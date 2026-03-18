# app/models/permission.py

from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base


# ── Permission ────────────────────────────────────────────────────────────────
# Each row is one permission string, e.g. "users:read", "billing:manage".
# Permissions are global (not per-tenant) — roles per tenant reference them.

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, unique=True, nullable=False, index=True)
    # Examples:
    #   users:read        users:write       users:delete
    #   projects:read     projects:write    projects:delete
    #   billing:read      billing:manage
    #   roles:read        roles:manage
    #   tenant:manage

    description = Column(String, nullable=True)

    role_permissions = relationship("RolePermission", back_populates="permission")


# ── RolePermission (join table) ───────────────────────────────────────────────

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)

    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    # ── relationships ────────────────────────────────────────────
    role = relationship("Role", back_populates="role_permissions")

    permission = relationship("Permission", back_populates="role_permissions")