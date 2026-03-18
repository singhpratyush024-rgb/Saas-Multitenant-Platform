# app/api/routes/tasks.py
# Nested under /projects/{project_id}/tasks

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ForbiddenException
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import require_permission
from app.db.task_repository import TaskRepository
from app.db.cache import TenantCache
from app.db.project_repository import ProjectRepository
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from app.schemas.response import single, paginated
from app.services.audit import write_audit

router = APIRouter()


def _cache(tenant_id: int, project_id: int) -> TenantCache:
    return TenantCache(
        tenant_id=tenant_id,
        prefix=f"tasks:project:{project_id}",
        ttl=300,
    )


async def _get_project_or_404(project_id: int, tenant: Tenant, db: AsyncSession):
    repo = ProjectRepository(db, tenant.id)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundException(resource="Project")
    return project


# ── POST /projects/{project_id}/tasks ────────────────────────────

@router.post("/projects/{project_id}/tasks/")
async def create_task(
    project_id: int,
    data: TaskCreate,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:write")),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_or_404(project_id, tenant, db)

    repo = TaskRepository(db, tenant.id, project_id)
    task = await repo.create(
        title=data.title,
        description=data.description,
        assignee_id=data.assignee_id,
        status=data.status,
    )

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="task",
        resource_id=task.id,
        action="create",
        after=TaskResponse.model_validate(task).model_dump(mode="json"),
    )

    await db.commit()
    await db.refresh(task)
    await _cache(tenant.id, project_id).invalidate()

    return single(TaskResponse.model_validate(task).model_dump())


# ── GET /projects/{project_id}/tasks ─────────────────────────────

@router.get("/projects/{project_id}/tasks/")
async def list_tasks(
    project_id: int,
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_or_404(project_id, tenant, db)

    cache_key = f"list:cursor={cursor}:limit={limit}:status={status}:sort={sort_by}:{sort_dir}"
    cache = _cache(tenant.id, project_id)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    repo = TaskRepository(db, tenant.id, project_id)
    filters = {}
    if status:
        filters["status"] = status

    items, total, next_cursor = await repo.list(
        cursor=cursor,
        limit=limit,
        filters=filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    response = paginated(
        items=items,
        total=total,
        limit=limit,
        next_cursor=next_cursor,
        serializer=TaskResponse,
    )
    await cache.set(cache_key, response)
    return response


# ── GET /projects/{project_id}/tasks/{task_id} ───────────────────

@router.get("/projects/{project_id}/tasks/{task_id}")
async def get_task(
    project_id: int,
    task_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_or_404(project_id, tenant, db)

    cache = _cache(tenant.id, project_id)
    cached = await cache.get(f"detail:{task_id}")
    if cached:
        return cached

    repo = TaskRepository(db, tenant.id, project_id)
    task = await repo.get(task_id)
    if not task:
        raise NotFoundException(resource="Task")

    response = single(TaskResponse.model_validate(task).model_dump())
    await cache.set(f"detail:{task_id}", response)
    return response


# ── PATCH /projects/{project_id}/tasks/{task_id} ─────────────────

@router.patch("/projects/{project_id}/tasks/{task_id}")
async def update_task(
    project_id: int,
    task_id: int,
    data: TaskUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:write")),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_or_404(project_id, tenant, db)

    repo = TaskRepository(db, tenant.id, project_id)
    task = await repo.get(task_id)
    if not task:
        raise NotFoundException(resource="Task")

    before = TaskResponse.model_validate(task).model_dump(mode="json")
    updates = data.model_dump(exclude_unset=True)
    task = await repo.update(task_id, **updates)

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="task",
        resource_id=task_id,
        action="update",
        before=before,
        after=TaskResponse.model_validate(task).model_dump(mode="json"),
    )

    await db.commit()
    await db.refresh(task)

    cache = _cache(tenant.id, project_id)
    await cache.invalidate(f"detail:{task_id}")
    await cache.invalidate()

    return single(TaskResponse.model_validate(task).model_dump())


# ── DELETE /projects/{project_id}/tasks/{task_id} ────────────────

@router.delete("/projects/{project_id}/tasks/{task_id}")
async def delete_task(
    project_id: int,
    task_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:delete")),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_or_404(project_id, tenant, db)

    repo = TaskRepository(db, tenant.id, project_id)
    task = await repo.get(task_id)
    if not task:
        raise NotFoundException(resource="Task")

    before = TaskResponse.model_validate(task).model_dump(mode="json")
    await repo.delete(task_id)

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="task",
        resource_id=task_id,
        action="delete",
        before=before,
    )

    await db.commit()

    cache = _cache(tenant.id, project_id)
    await cache.invalidate(f"detail:{task_id}")
    await cache.invalidate()

    return single({"id": task_id, "deleted": True})