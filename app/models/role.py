# app/models/role.py

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)                          # owner / admin / member

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    is_default = Column(Boolean, default=False)                    # auto-assigned on registration

    # ── relationships ────────────────────────────────────────────
    tenant = relationship("Tenant", back_populates="roles")

    role_permissions = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
    )

    users = relationship("User", back_populates="role_rel")