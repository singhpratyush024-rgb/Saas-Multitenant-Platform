# app/dependencies/auth.py

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import SECRET_KEY, ALGORITHM
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.exceptions import (
    InvalidTokenException,
    TokenBlacklistedException,
    UnauthorizedException,
)
from app.models.tenant import Tenant
from app.models.user import User


security = HTTPBearer(auto_error=True)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:

    token = credentials.credentials

    # Check Redis blacklist (logout support)
    blacklisted = await redis_client.get(f"blacklist:{token}")
    if blacklisted:
        raise TokenBlacklistedException()

    # Decode JWT
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise InvalidTokenException(detail="Token has expired")
    except JWTError:
        raise InvalidTokenException(detail="Invalid token")

    user_id = payload.get("user_id")
    if not user_id:
        raise InvalidTokenException(detail="Invalid token payload")

    # Load user from DB
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException(detail="User not found")

    # Cross-tenant isolation: verify token's tenant matches the request header
    tenant_slug = request.headers.get("X-Tenant-ID")
    if tenant_slug:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.slug == tenant_slug)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is not None and user.tenant_id != tenant.id:
            raise UnauthorizedException(
                detail="Token does not belong to the requested tenant"
            )

    return user