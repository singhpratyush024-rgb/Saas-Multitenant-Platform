# app/services/seed_plans.py
#
# Call once at startup or via migration to seed plan definitions.
# Update stripe_price_id values after creating products in Stripe dashboard.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.plan import Plan


PLANS = [
    {
        "key": "free",
        "name": "Free",
        "stripe_price_id": None,          # No Stripe price for free plan
        "price_usd_cents": 0,
        "limits": {
            "max_members": 3,
            "max_projects": 5,
            "max_storage_mb": 100,
            "can_invite": True,
            "can_use_api": False,
            "support_level": "community",
        },
    },
    {
        "key": "starter",
        "name": "Starter",
        "stripe_price_id": "prod_UB0exhsGIUPcvY",   # replace with real Stripe price id
        "price_usd_cents": 2900,          # $29/month
        "limits": {
            "max_members": 10,
            "max_projects": 25,
            "max_storage_mb": 1000,
            "can_invite": True,
            "can_use_api": True,
            "support_level": "email",
        },
    },
    {
        "key": "pro",
        "name": "Pro",
        "stripe_price_id": "prod_UB0fgpqBKsYmqZ",       # replace with real Stripe price id
        "price_usd_cents": 9900,          # $99/month
        "limits": {
            "max_members": 50,
            "max_projects": 100,
            "max_storage_mb": 10000,
            "can_invite": True,
            "can_use_api": True,
            "support_level": "priority",
        },
    },
    {
        "key": "enterprise",
        "name": "Enterprise",
        "stripe_price_id": "prod_UB0hxg9wIr46jA",
        "price_usd_cents": 29900,         # $299/month
        "limits": {
            "max_members": -1,            # -1 = unlimited
            "max_projects": -1,
            "max_storage_mb": -1,
            "can_invite": True,
            "can_use_api": True,
            "support_level": "dedicated",
        },
    },
]


async def seed_plans(db: AsyncSession) -> None:
    """Idempotent — safe to call multiple times."""
    for plan_data in PLANS:
        result = await db.execute(
            select(Plan).where(Plan.key == plan_data["key"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            db.add(Plan(**plan_data))
        else:
            # Update limits and price in case they changed
            existing.limits = plan_data["limits"]
            existing.price_usd_cents = plan_data["price_usd_cents"]
            if plan_data["stripe_price_id"]:
                existing.stripe_price_id = plan_data["stripe_price_id"]

    await db.commit()