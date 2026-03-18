# app/api/routes/members.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    ConflictException,
)
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import (
    require_permission,
    owner_only,
    _get_user_permissions,
)
from app.models.user import User
from app.models.role import Role
from app.models.tenant import Tenant
from app.schemas.user import (
    MemberResponse,
    PaginatedMembers,
    RoleUpdateRequest,
    ProfileResponse,
)

router = APIRouter(prefix="/members", tags=["members"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_member_in_tenant(
    member_id: int,
    tenant: Tenant,
    db: AsyncSession,
) -> User:
    """Fetch a user by id scoped to the current tenant. Raises 404 if not found."""
    result = await db.execute(
        select(User).where(
            User.id == member_id,
            User.tenant_id == tenant.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise NotFoundException(resource="Member")
    return member


# ── GET /members/me — current user profile + permissions ─────────────────────

@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await _get_user_permissions(current_user, db)
    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        role_id=current_user.role_id,
        is_active=current_user.is_active,
        tenant_id=current_user.tenant_id,
        permissions=sorted(permissions),
    )


# ── GET /members — list all members with pagination ───────────────────────────

@router.get("/", response_model=PaginatedMembers)
async def list_members(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("users:read")),
    db: AsyncSession = Depends(get_db),
):
    # Total count
    count_result = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant.id)
    )
    total = count_result.scalar()

    # Paginated results
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User)
        .where(User.tenant_id == tenant.id)
        .order_by(User.id)
        .offset(offset)
        .limit(page_size)
    )
    members = result.scalars().all()

    return PaginatedMembers(
        total=total,
        page=page,
        page_size=page_size,
        items=[MemberResponse.model_validate(m) for m in members],
    )


# ── PATCH /members/{id}/role — change member role, owner only ────────────────

@router.patch("/{member_id}/role", response_model=MemberResponse)
async def update_member_role(
    member_id: int,
    data: RoleUpdateRequest,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(owner_only()),
    db: AsyncSession = Depends(get_db),
):
    # Cannot change your own role
    if member_id == current_user.id:
        raise ForbiddenException(
            detail="You cannot change your own role"
        )

    # Fetch the member
    member = await _get_member_in_tenant(member_id, tenant, db)

    # Validate new role exists and belongs to this tenant
    role_result = await db.execute(
        select(Role).where(
            Role.id == data.role_id,
            Role.tenant_id == tenant.id,
        )
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise NotFoundException(resource="Role")

    # Cannot demote another owner if they are the last owner
    if member.role == "owner" and role.name != "owner":
        owner_count_result = await db.execute(
            select(func.count(User.id)).where(
                User.tenant_id == tenant.id,
                User.role == "owner",
            )
        )
        owner_count = owner_count_result.scalar()
        if owner_count <= 1:
            raise ConflictException(
                detail="Cannot demote the last owner of the tenant"
            )

    # Apply role change
    member.role = role.name
    member.role_id = role.id
    await db.commit()
    await db.refresh(member)

    return member


# ── DELETE /members/{id} — remove member from tenant ─────────────────────────

@router.delete("/{member_id}")
async def remove_member(
    member_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("users:delete")),
    db: AsyncSession = Depends(get_db),
):
    # Cannot remove yourself
    if member_id == current_user.id:
        raise ForbiddenException(
            detail="You cannot remove yourself from the tenant"
        )

    # Fetch the member
    member = await _get_member_in_tenant(member_id, tenant, db)

    # Cannot remove an owner
    if member.role == "owner":
        raise ForbiddenException(
            detail="Cannot remove an owner from the tenant. "
                   "Transfer ownership first."
        )

    await db.delete(member)
    await db.commit()

    return {"message": f"Member {member.email} removed from tenant"}