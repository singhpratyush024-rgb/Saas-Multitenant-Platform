# app/api/routes/auth.py

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    SECRET_KEY,
    ALGORITHM,
)
from app.core.redis import redis_client
from app.core.exceptions import (
    UserAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
)

from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.schemas.user import UserCreate, UserLogin
from app.dependencies.tenant import get_current_tenant
from app.services.seed_roles import DEFAULT_ROLE_NAME


router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


# ------------------------------------------------------------------
# Register
# ------------------------------------------------------------------
@router.post("/register")
async def register_user(
    data: UserCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Duplicate check
    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.tenant_id == tenant.id,
        )
    )
    if result.scalar_one_or_none():
        raise UserAlreadyExistsException()

    # Look up the default role for this tenant (member)
    role_result = await db.execute(
        select(Role).where(
            Role.tenant_id == tenant.id,
            Role.name == DEFAULT_ROLE_NAME,
        )
    )
    default_role = role_result.scalar_one_or_none()

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        tenant_id=tenant.id,
        role=DEFAULT_ROLE_NAME,
        role_id=default_role.id if default_role else None,
    )

    db.add(user)
    await db.commit()

    return {"message": "User created successfully"}


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------
@router.post("/login")
async def login(
    data: UserLogin,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.tenant_id == tenant.id,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise InvalidCredentialsException()

    access_token = create_access_token(
        {"user_id": user.id, "tenant_id": tenant.id, "role": user.role}
    )
    refresh_token = create_refresh_token(
        {"user_id": user.id, "tenant_id": tenant.id}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ------------------------------------------------------------------
# Refresh Token
# ------------------------------------------------------------------
@router.post("/refresh")
async def refresh_token(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise InvalidTokenException(detail="Invalid or expired refresh token")

    new_access_token = create_access_token(
        {
            "user_id": payload.get("user_id"),
            "tenant_id": payload.get("tenant_id"),
        }
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


# ------------------------------------------------------------------
# Logout (Token Blacklist)
# ------------------------------------------------------------------
@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    await redis_client.set(f"blacklist:{token}", "true", ex=3600)
    return {"message": "Logged out successfully"}