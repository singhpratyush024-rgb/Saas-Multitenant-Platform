# app/api/routes/invitations.py

import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.core.security import hash_password
from app.core.config import settings
from app.core.redis import redis_client
from app.core.email import send_invitation_email
from app.core.exceptions import (
    UserAlreadyExistsException,
    NotFoundException,
    InvitationNotFoundException,
    InvitationExpiredException,
    InvitationAlreadyAcceptedException,
    InvitationAlreadyExistsException,
    RateLimitExceededException,
)
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import admin_or_owner
from app.models.invitation import Invitation
from app.models.user import User
from app.models.role import Role
from app.models.tenant import Tenant
from app.schemas.invitation import InvitationCreate, InvitationResponse, InvitationAccept

INVITATION_EXPIRE_HOURS = 48
RESEND_RATE_LIMIT_SECONDS = 300   # 5 minutes between resends per invitation

router = APIRouter(prefix="/invitations", tags=["invitations"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_accept_url(token: str) -> str:
    return f"{settings.APP_BASE_URL}/invitations/accept?token={token}"


async def _send_invite(
    *,
    invitation: Invitation,
    tenant: Tenant,
    inviter: User,
    role: Role,
) -> None:
    """Build accept URL and fire the invitation email."""
    await send_invitation_email(
        to_email=invitation.email,
        tenant_name=tenant.name,
        inviter_email=inviter.email,
        role_name=role.name,
        accept_url=_build_accept_url(invitation.token),
        expires_hours=INVITATION_EXPIRE_HOURS,
    )


# ── POST /invitations — create and send ──────────────────────────────────────

@router.post("/", response_model=InvitationResponse)
async def create_invitation(
    data: InvitationCreate,
    tenant: Tenant = Depends(get_current_tenant),
    inviter: User = Depends(admin_or_owner()),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate role exists and belongs to this tenant
    role_result = await db.execute(
        select(Role).where(
            Role.id == data.role_id,
            Role.tenant_id == tenant.id,
        )
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise NotFoundException(resource="Role")

    # 2. Check email not already a user in this tenant
    user_result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.tenant_id == tenant.id,
        )
    )
    if user_result.scalar_one_or_none():
        raise UserAlreadyExistsException(
            detail=f"{data.email} is already a member of this tenant"
        )

    # 3. Check no pending unexpired invitation already exists
    now = datetime.now(timezone.utc)
    existing_result = await db.execute(
        select(Invitation).where(
            and_(
                Invitation.email == data.email,
                Invitation.tenant_id == tenant.id,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > now,
            )
        )
    )
    if existing_result.scalar_one_or_none():
        raise InvitationAlreadyExistsException()

    # 4. Generate token and store invitation
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=INVITATION_EXPIRE_HOURS)

    invitation = Invitation(
        email=data.email,
        tenant_id=tenant.id,
        role_id=data.role_id,
        token=token,
        expires_at=expires_at,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # 5. Send invitation email
    await _send_invite(
        invitation=invitation,
        tenant=tenant,
        inviter=inviter,
        role=role,
    )

    return invitation


# ── POST /invitations/{id}/resend — resend with rate limit ────────────────────

@router.post("/{invitation_id}/resend", response_model=InvitationResponse)
async def resend_invitation(
    invitation_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    inviter: User = Depends(admin_or_owner()),
    db: AsyncSession = Depends(get_db),
):
    # 1. Fetch invitation
    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.tenant_id == tenant.id,
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise InvitationNotFoundException()

    # 2. Cannot resend an accepted invitation
    if invitation.accepted_at is not None:
        raise InvitationAlreadyAcceptedException(
            detail="Cannot resend an invitation that has already been accepted"
        )

    # 3. Rate limit — one resend per invitation per 5 minutes
    rate_key = f"resend_invite:{invitation.id}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, RESEND_RATE_LIMIT_SECONDS)
    if count > 1:
        ttl = await redis_client.ttl(rate_key)
        raise RateLimitExceededException(
            detail=f"Please wait {ttl} seconds before resending this invitation"
        )

    # 4. If expired, refresh the token and expiry
    now = datetime.now(timezone.utc)
    if invitation.expires_at < now:
        invitation.token = secrets.token_urlsafe(32)
        invitation.expires_at = now + timedelta(hours=INVITATION_EXPIRE_HOURS)
        await db.commit()
        await db.refresh(invitation)

    # 5. Fetch role
    role_result = await db.execute(
        select(Role).where(Role.id == invitation.role_id)
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise NotFoundException(resource="Role")

    # 6. Resend email
    await _send_invite(
        invitation=invitation,
        tenant=tenant,
        inviter=inviter,
        role=role,
    )

    return invitation


# ── POST /invitations/accept — public, validate token and create user ─────────

@router.post("/accept")
async def accept_invitation(
    data: InvitationAccept,
    db: AsyncSession = Depends(get_db),
):
    # 1. Look up invitation by token
    result = await db.execute(
        select(Invitation).where(Invitation.token == data.token)
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise InvitationNotFoundException()

    # 2. Check already accepted
    if invitation.accepted_at is not None:
        raise InvitationAlreadyAcceptedException()

    # 3. Check expiry
    now = datetime.now(timezone.utc)
    if invitation.expires_at < now:
        raise InvitationExpiredException()

    # 4. Check email not already registered in this tenant
    user_result = await db.execute(
        select(User).where(
            User.email == invitation.email,
            User.tenant_id == invitation.tenant_id,
        )
    )
    if user_result.scalar_one_or_none():
        raise UserAlreadyExistsException(
            detail=f"{invitation.email} is already a member of this tenant"
        )

    # 5. Look up role name
    role_name = "member"
    if invitation.role_id:
        role_result = await db.execute(
            select(Role).where(Role.id == invitation.role_id)
        )
        role = role_result.scalar_one_or_none()
        if role:
            role_name = role.name

    # 6. Create user
    user = User(
        email=invitation.email,
        hashed_password=hash_password(data.password),
        tenant_id=invitation.tenant_id,
        role=role_name,
        role_id=invitation.role_id,
    )
    db.add(user)

    # 7. Mark invitation accepted
    invitation.accepted_at = now
    await db.commit()

    return {"message": f"Welcome! Account created for {invitation.email}"}


# ── GET /invitations — admin+ only, list all ──────────────────────────────────

@router.get("/", response_model=list[InvitationResponse])
async def list_invitations(
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(admin_or_owner()),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invitation)
        .where(Invitation.tenant_id == tenant.id)
        .order_by(Invitation.created_at.desc())
    )
    return result.scalars().all()