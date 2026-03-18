# app/models/tenant.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    slug = Column(String, unique=True, nullable=False, index=True)

    plan = Column(String, default="free")

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ── relationships ────────────────────────────────────────────
    users = relationship("User", back_populates="tenant")

    roles = relationship(
        "Role",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )