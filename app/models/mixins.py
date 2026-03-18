from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.sql import func

class TenantMixin:
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )


class TimestampMixin:
    """Adds created_at and updated_at to any model."""
 
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
 
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
