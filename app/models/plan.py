# app/models/plan.py
#
# Stores plan definitions with feature limits.
# Seeded once at startup — not user-editable.

from sqlalchemy import Column, Integer, String, Boolean, JSON
from app.models.base import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)

    # Internal key: "free" | "starter" | "pro" | "enterprise"
    key = Column(String, unique=True, nullable=False, index=True)

    name = Column(String, nullable=False)              # Display name

    stripe_price_id = Column(String, nullable=True)    # e.g. price_xxx from Stripe

    price_usd_cents = Column(Integer, default=0)       # monthly price in cents

    is_active = Column(Boolean, default=True)

    # Feature limits stored as JSON for flexibility
    # {
    #   "max_members": 3,
    #   "max_projects": 5,
    #   "max_storage_mb": 100,
    #   "can_invite": true,
    #   "can_use_api": false,
    #   "support_level": "community"
    # }
    limits = Column(JSON, nullable=False, default=dict)