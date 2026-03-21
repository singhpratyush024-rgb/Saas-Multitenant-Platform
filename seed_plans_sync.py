# Run this once to seed plans into the DB
# python seed_plans_sync.py

import os
import sys
import json

sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

# Fix Docker hostname → localhost for local execution
os.environ["SYNC_DATABASE_URL"] = os.getenv(
    "SYNC_DATABASE_URL", ""
).replace("@db:", "@localhost:")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

SYNC_DATABASE_URL = os.environ["SYNC_DATABASE_URL"]

# ✅ limits as Python dicts
PLANS = [
    {
        "key": "free",
        "name": "Free",
        "stripe_price_id": None,
        "price_usd_cents": 0,
        "is_active": True,
        "limits": {
            "max_members": 3,
            "max_projects": 5,
            "max_storage_mb": 100,
            "can_invite": True,
            "can_use_api": False,
            "support_level": "community"
        },
    },
    {
        "key": "starter",
        "name": "Starter",
        "stripe_price_id": "price_starter_monthly",
        "price_usd_cents": 2900,
        "is_active": True,
        "limits": {
            "max_members": 10,
            "max_projects": 25,
            "max_storage_mb": 1000,
            "can_invite": True,
            "can_use_api": True,
            "support_level": "email"
        },
    },
    {
        "key": "pro",
        "name": "Pro",
        "stripe_price_id": "price_pro_monthly",
        "price_usd_cents": 9900,
        "is_active": True,
        "limits": {
            "max_members": 50,
            "max_projects": 100,
            "max_storage_mb": 10000,
            "can_invite": True,
            "can_use_api": True,
            "support_level": "priority"
        },
    },
    {
        "key": "enterprise",
        "name": "Enterprise",
        "stripe_price_id": "price_enterprise_monthly",
        "price_usd_cents": 29900,
        "is_active": True,
        "limits": {
            "max_members": -1,
            "max_projects": -1,
            "max_storage_mb": -1,
            "can_invite": True,
            "can_use_api": True,
            "support_level": "dedicated"
        },
    },
]

engine = create_engine(SYNC_DATABASE_URL, echo=True)

with Session(engine) as db:
    for plan in PLANS:

        existing = db.execute(
            text("SELECT id FROM plans WHERE key = :key"),
            {"key": plan["key"]}
        ).fetchone()

        if not existing:
            db.execute(
                text("""
                    INSERT INTO plans (
                        key, name, stripe_price_id,
                        price_usd_cents, is_active, limits
                    )
                    VALUES (
                        :key, :name, :stripe_price_id,
                        :price_usd_cents, :is_active,
                        CAST(:limits AS jsonb)
                    )
                """),
                {
                    **plan,
                    "limits": json.dumps(plan["limits"])  # ✅ REQUIRED
                }
            )
            print(f"Inserted plan: {plan['key']}")

        else:
            db.execute(
                text("""
                    UPDATE plans SET
                        limits = CAST(:limits AS jsonb),
                        price_usd_cents = :price_usd_cents,
                        stripe_price_id = COALESCE(:stripe_price_id, stripe_price_id)
                    WHERE key = :key
                """),
                {
                    **plan,
                    "limits": json.dumps(plan["limits"])  # ✅ REQUIRED
                }
            )
            print(f"Updated plan: {plan['key']}")

    db.commit()

print("✅ Done — plans seeded successfully")