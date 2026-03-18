# app/models/project.py

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    owner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    name = Column(String, nullable=False, index=True)

    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    # ── relationships ─────────────────────────────────────────────
    tenant = relationship("Tenant")
    owner = relationship("User")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    files = relationship("FileUpload")