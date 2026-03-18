# app/models/task.py

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assignee_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    title = Column(String, nullable=False, index=True)

    description = Column(Text, nullable=True)

    status = Column(String, default="todo", nullable=False)
    # Values: todo | in_progress | done

    is_active = Column(Boolean, default=True, nullable=False)

    # ── relationships ─────────────────────────────────────────────
    tenant = relationship("Tenant")
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User")