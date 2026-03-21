

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.dependencies.tenant import get_current_tenant
from app.models.tenant import Tenant
from app.models.plan import Plan


async def _get_tenant_plan(tenant: Tenant, db: AsyncSession) -> Plan | None:
    """Return the Plan object for the tenant's current plan key."""
    result = await db.execute(
        select(Plan).where(Plan.key == tenant.plan, Plan.is_active == True)
    )
    return result.scalar_one_or_none()


def require_plan_feature(feature: str):
    """
    Gate a route behind a boolean plan feature.

    Example features: "can_invite", "can_use_api"

    Usage:
        @router.post("/invite")
        async def invite(_=Depends(require_plan_feature("can_invite"))):
    """
    async def dependency(
        tenant: Tenant = Depends(get_current_tenant),
        db: AsyncSession = Depends(get_db),
    ):
        plan = await _get_tenant_plan(tenant, db)
        if not plan:
            return  # No plan record — allow (fail open for free tier)

        if not plan.limits.get(feature, False):
            raise ForbiddenException(
                detail=f"Your current plan ({tenant.plan}) does not include '{feature}'. "
                       f"Please upgrade to access this feature."
            )

    return dependency


def require_plan_limit(limit_key: str, count_fn):
    """
    Gate a route behind a numeric plan limit.

    count_fn is an async callable (db, tenant_id) -> int
    that returns the current usage count.

    Usage:
        async def _count_members(db, tenant_id):
            result = await db.execute(
                select(func.count(User.id)).where(User.tenant_id == tenant_id)
            )
            return result.scalar()

        @router.post("/members")
        async def add_member(
            _=Depends(require_plan_limit("max_members", _count_members))
        ):
    """
    async def dependency(
        tenant: Tenant = Depends(get_current_tenant),
        db: AsyncSession = Depends(get_db),
    ):
        plan = await _get_tenant_plan(tenant, db)
        if not plan:
            return

        limit = plan.limits.get(limit_key, -1)
        if limit == -1:
            return  # -1 = unlimited

        current_count = await count_fn(db, tenant.id)
        if current_count >= limit:
            raise ForbiddenException(
                detail=f"You have reached the {limit_key} limit ({limit}) "
                       f"for your {tenant.plan} plan. Please upgrade to add more."
            )

    return dependency


# ── Convenience shortcuts ─────────────────────────────────────────────────────

def require_api_access():
    return require_plan_feature("can_use_api")


def require_invite_access():
    return require_plan_feature("can_invite")