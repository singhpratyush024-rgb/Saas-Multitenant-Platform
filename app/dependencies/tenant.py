# app/dependencies/tenant.py
#
# Tenant DB lookup now lives here as a FastAPI dependency,
# using the same get_db session as all other route dependencies.
# This eliminates the connection conflict caused by the middleware
# opening a second engine.

from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.exceptions import (
    TenantHeaderMissingException,
    TenantNotFoundException,
    TenantInactiveException,
)
from app.models.tenant import Tenant


async def get_current_tenant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tenant:

    tenant_slug = request.headers.get("X-Tenant-ID")

    if not tenant_slug:
        raise TenantHeaderMissingException()

    result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise TenantNotFoundException()

    if not tenant.is_active:
        raise TenantInactiveException()

    return tenant