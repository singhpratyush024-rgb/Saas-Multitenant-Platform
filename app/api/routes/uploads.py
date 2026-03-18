# app/api/routes/uploads.py

import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ForbiddenException
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import require_permission
from app.db.project_repository import ProjectRepository
from app.models.file_upload import FileUpload
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.response import single
from app.services.storage import (
    get_storage,
    generate_stored_filename,
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/projects/{project_id}/files", tags=["uploads"])


# ── POST /projects/{project_id}/files ────────────────────────────

@router.post("/")
async def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:write")),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate project belongs to tenant
    project_repo = ProjectRepository(db, tenant.id)
    project = await project_repo.get(project_id)
    if not project:
        raise NotFoundException(resource="Project")

    # 2. Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. "
                   f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    # 3. Read and validate size
    data = await file.read()
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
        )

    # 4. Generate unique stored filename and save
    stored_filename = generate_stored_filename(file.filename)
    storage = get_storage()
    storage_path = await storage.save(data, stored_filename)

    # 5. Record in DB
    upload = FileUpload(
        tenant_id=tenant.id,
        uploaded_by=current_user.id,
        project_id=project_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        content_type=file.content_type,
        size_bytes=len(data),
        storage_path=storage_path,
    )
    db.add(upload)

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="file_upload",
        resource_id=None,
        action="create",
        after={
            "original_filename": file.filename,
            "size_bytes": len(data),
            "content_type": file.content_type,
        },
    )

    await db.commit()
    await db.refresh(upload)

    return single({
        "id": upload.id,
        "original_filename": upload.original_filename,
        "content_type": upload.content_type,
        "size_bytes": upload.size_bytes,
        "url": storage.public_url(storage_path),
    })


# ── GET /projects/{project_id}/files ─────────────────────────────

@router.get("/")
async def list_files(
    project_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    project_repo = ProjectRepository(db, tenant.id)
    project = await project_repo.get(project_id)
    if not project:
        raise NotFoundException(resource="Project")

    result = await db.execute(
        select(FileUpload).where(
            FileUpload.tenant_id == tenant.id,
            FileUpload.project_id == project_id,
        ).order_by(FileUpload.id.desc())
    )
    files = result.scalars().all()
    storage = get_storage()

    return single([
        {
            "id": f.id,
            "original_filename": f.original_filename,
            "content_type": f.content_type,
            "size_bytes": f.size_bytes,
            "url": storage.public_url(f.storage_path),
            "uploaded_by": f.uploaded_by,
        }
        for f in files
    ])


# ── DELETE /projects/{project_id}/files/{file_id} ────────────────

@router.delete("/{file_id}")
async def delete_file(
    project_id: int,
    file_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(require_permission("projects:delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FileUpload).where(
            FileUpload.id == file_id,
            FileUpload.tenant_id == tenant.id,
            FileUpload.project_id == project_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise NotFoundException(resource="File")

    storage = get_storage()
    await storage.delete(upload.storage_path)

    await write_audit(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        resource_type="file_upload",
        resource_id=file_id,
        action="delete",
        before={"original_filename": upload.original_filename},
    )

    await db.delete(upload)
    await db.commit()

    return single({"id": file_id, "deleted": True})