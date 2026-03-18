# app/api/routes/search.py
#
# PostgreSQL full-text search across projects and tasks.
# Uses to_tsvector + plainto_tsquery for proper FTS.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, text

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.models.project import Project
from app.models.task import Task
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.response import single

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
async def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Full-text search across projects and tasks for the current tenant.
    Uses PostgreSQL plainto_tsquery for natural language queries.
    """

    # ── Search projects ───────────────────────────────────────────
    project_results = await db.execute(
        select(Project)
        .where(
            Project.tenant_id == tenant.id,
            or_(
                func.to_tsvector("english", Project.name).op("@@")(
                    func.plainto_tsquery("english", q)
                ),
                func.to_tsvector("english", func.coalesce(Project.description, "")).op("@@")(
                    func.plainto_tsquery("english", q)
                ),
            ),
        )
        .limit(limit)
    )
    projects = project_results.scalars().all()

    # ── Search tasks ──────────────────────────────────────────────
    task_results = await db.execute(
        select(Task)
        .where(
            Task.tenant_id == tenant.id,
            or_(
                func.to_tsvector("english", Task.title).op("@@")(
                    func.plainto_tsquery("english", q)
                ),
                func.to_tsvector("english", func.coalesce(Task.description, "")).op("@@")(
                    func.plainto_tsquery("english", q)
                ),
            ),
        )
        .limit(limit)
    )
    tasks = task_results.scalars().all()

    return single({
        "query": q,
        "results": {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "type": "project",
                }
                for p in projects
            ],
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "project_id": t.project_id,
                    "status": t.status,
                    "type": "task",
                }
                for t in tasks
            ],
            "total": len(projects) + len(tasks),
        },
    })


# ── GET /audit-logs — list audit trail for tenant ─────────────────────────────

from app.models.audit_log import AuditLog
from app.dependencies.permission import admin_or_owner

audit_router = APIRouter(prefix="/audit-logs", tags=["audit"])


@audit_router.get("/")
async def list_audit_logs(
    resource_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(admin_or_owner()),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).where(
        AuditLog.tenant_id == tenant.id
    )
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if action:
        query = query.where(AuditLog.action == action)

    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return single([
        {
            "id": log.id,
            "user_id": log.user_id,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "action": log.action,
            "diff": log.diff,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ])