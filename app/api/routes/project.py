# app/api/routes/project.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import require_permission
from app.db.project_repository import ProjectRepository
from app.db.cache import TenantCache
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.schemas.response import single, paginated
from app.services.audit import write_audit

router = APIRouter(prefix="/projects", tags=["projects"])

CACHE_PREFIX = "projects"
CACHE_TTL = 300


def _cache(tenant_id: int) -> TenantCache:
    return TenantCache(tenant_id=tenant_id, prefix=CACHE_PREFIX, ttl=CACHE_TTL)


@router.post("/")
async def create_project(
    data: ProjectCreate,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:write")),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db, tenant.id)
    project = await repo.create(
        name=data.name,
        description=data.description,
        owner_id=current_user.id,
    )

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="project",
        resource_id=project.id,
        action="create",
        after=ProjectResponse.model_validate(project).model_dump(mode="json"),
    )

    await db.commit()
    await db.refresh(project)
    await _cache(tenant.id).invalidate()

    return single(ProjectResponse.model_validate(project).model_dump())


@router.get("/")
async def list_projects(
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    name: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"list:cursor={cursor}:limit={limit}:name={name}:active={is_active}:sort={sort_by}:{sort_dir}"
    cache = _cache(tenant.id)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    repo = ProjectRepository(db, tenant.id)
    filters = {}
    if name is not None:
        filters["name"] = name
    if is_active is not None:
        filters["is_active"] = is_active

    items, total, next_cursor = await repo.list(
        cursor=cursor, limit=limit, filters=filters,
        sort_by=sort_by, sort_dir=sort_dir,
    )

    response = paginated(
        items=items, total=total, limit=limit,
        next_cursor=next_cursor, serializer=ProjectResponse,
    )
    await cache.set(cache_key, response)
    return response


@router.get("/{project_id}")
async def get_project(
    project_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"detail:{project_id}"
    cache = _cache(tenant.id)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    repo = ProjectRepository(db, tenant.id)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundException(resource="Project")

    response = single(ProjectResponse.model_validate(project).model_dump())
    await cache.set(cache_key, response)
    return response


@router.patch("/{project_id}")
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:write")),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db, tenant.id)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundException(resource="Project")

    before = ProjectResponse.model_validate(project).model_dump(mode="json")
    updates = data.model_dump(exclude_unset=True)
    project = await repo.update(project_id, **updates)

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="project",
        resource_id=project_id,
        action="update",
        before=before,
        after=ProjectResponse.model_validate(project).model_dump(mode="json"),
    )

    await db.commit()
    await db.refresh(project)

    cache = _cache(tenant.id)
    await cache.invalidate(f"detail:{project_id}")
    await cache.invalidate()

    return single(ProjectResponse.model_validate(project).model_dump())


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:delete")),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db, tenant.id)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundException(resource="Project")

    before = ProjectResponse.model_validate(project).model_dump(mode="json")
    await repo.delete(project_id)

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="project",
        resource_id=project_id,
        action="delete",
        before=before,
    )

    await db.commit()

    cache = _cache(tenant.id)
    await cache.invalidate(f"detail:{project_id}")
    await cache.invalidate()

    return single({"id": project_id, "deleted": True})