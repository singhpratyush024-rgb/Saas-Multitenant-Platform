# app/models/audit_log.py

from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # e.g. "project", "task", "invitation", "member"
    resource_type = Column(String, nullable=False, index=True)

    # The id of the affected record
    resource_id = Column(Integer, nullable=True)

    # e.g. "create", "update", "delete"
    action = Column(String, nullable=False, index=True)

    # Full snapshot of changes: {"before": {...}, "after": {...}}
    diff = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── relationships ─────────────────────────────────────────────
    tenant = relationship("Tenant")
    user = relationship("User")