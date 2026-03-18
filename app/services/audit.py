# app/services/audit.py
#
# Call write_audit() after any write operation.
# It runs fire-and-forget so it never blocks the response.
#
# Usage:
#   await write_audit(
#       db=db,
#       tenant_id=tenant.id,
#       user_id=current_user.id,
#       resource_type="project",
#       resource_id=project.id,
#       action="create",
#       after=ProjectResponse.model_validate(project).model_dump(),
#   )

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog
import logging

logger = logging.getLogger(__name__)


async def write_audit(
    *,
    db: AsyncSession,
    tenant_id: int,
    user_id: int | None,
    resource_type: str,
    resource_id: int | None = None,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """
    Write a single audit log entry.
    Silently swallows errors so a logging failure never breaks a request.
    """
    try:
        diff = {}
        if before is not None:
            diff["before"] = before
        if after is not None:
            diff["after"] = after

        log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            diff=diff or None,
        )
        db.add(log)
        # No commit here — caller commits the main transaction
        # which includes the audit entry atomically
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)