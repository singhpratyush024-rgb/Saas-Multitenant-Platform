# app/api/routes/project.py

from fastapi import APIRouter, Depends, Header
from app.dependencies.auth import get_current_user
from app.dependencies.permission import (
    require_permission,
    require_role,
    admin_or_owner,
    owner_only,
)
from app.models.user import User

router = APIRouter(prefix="/projects", tags=["projects"])


# ── GET /projects/ ────────────────────────────────────────────────────────────
# Any authenticated user with projects:read can list projects
@router.get("/")
async def list_projects(
    x_tenant_id: str = Header(...),
    user: User = Depends(require_permission("projects:read")),
):
    return {
        "tenant": x_tenant_id,
        "user": user.email,
        "role": user.role,
    }


# ── POST /projects/ ───────────────────────────────────────────────────────────
# member, admin, owner can create projects
@router.post("/")
async def create_project(
    x_tenant_id: str = Header(...),
    user: User = Depends(require_permission("projects:write")),
):
    return {
        "message": "Project created",
        "created_by": user.email,
    }


# ── DELETE /projects/{project_id} ─────────────────────────────────────────────
# Only admin or owner can delete projects
@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    x_tenant_id: str = Header(...),
    user: User = Depends(require_permission("projects:delete")),
):
    return {
        "message": f"Project {project_id} deleted",
        "deleted_by": user.email,
    }


# ── GET /projects/admin ───────────────────────────────────────────────────────
# Admin panel — admin or owner only (role-based shortcut)
@router.get("/admin")
async def admin_panel(
    x_tenant_id: str = Header(...),
    user: User = Depends(admin_or_owner()),
):
    return {
        "message": "Welcome to the admin panel",
        "user": user.email,
        "role": user.role,
    }


# ── GET /projects/owner ───────────────────────────────────────────────────────
# Owner-only settings page
@router.get("/owner")
async def owner_settings(
    x_tenant_id: str = Header(...),
    user: User = Depends(owner_only()),
):
    return {
        "message": "Owner settings",
        "user": user.email,
    }


# ── GET /projects/billing ─────────────────────────────────────────────────────
# Billing management — owner only via permission check
@router.get("/billing")
async def billing(
    x_tenant_id: str = Header(...),
    user: User = Depends(require_permission("billing:manage")),
):
    return {
        "message": "Billing management",
        "user": user.email,
    }