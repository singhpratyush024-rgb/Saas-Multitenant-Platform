# app/api/routes/health.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.dependencies.tenant import get_current_tenant
from app.models.tenant import Tenant

router = APIRouter()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected", "tenant": tenant.slug}