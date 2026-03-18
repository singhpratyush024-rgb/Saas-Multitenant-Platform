from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tenant import Tenant


async def create_tenant(db: AsyncSession, name: str, slug: str, plan: str):
    tenant = Tenant(
        name=name,
        slug=slug,
        plan=plan
    )

    db.add(tenant)

    await db.commit()

    await db.refresh(tenant)

    return tenant


async def get_tenant_by_slug(db: AsyncSession, slug: str):

    result = await db.execute(
        select(Tenant).where(Tenant.slug == slug)
    )

    return result.scalar_one_or_none()