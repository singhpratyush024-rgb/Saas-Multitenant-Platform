# app/dependencies/permission.py
#
# Usage examples:
#
#   # Permission-based guard
#   @router.delete("/{id}")
#   async def delete_user(user = Depends(require_permission("users:delete"))):
#       ...
#
#   # Role-based shortcut
#   @router.post("/billing")
#   async def manage_billing(user = Depends(require_role("owner"))):
#       ...
#
#   # Admin OR owner
#   @router.get("/admin")
#   async def admin_panel(user = Depends(require_role("admin", "owner"))):
#       ...

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission, RolePermission


# ── Internal helper ───────────────────────────────────────────────────────────

async def _get_user_permissions(user: User, db: AsyncSession) -> set[str]:
    """
    Return the set of permission strings for the user's current role.
    Returns empty set if user has no role assigned.
    """
    if not user.role_id:
        return set()

    result = await db.execute(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == user.role_id)
    )

    return {row[0] for row in result.fetchall()}


async def _get_user_role_name(user: User, db: AsyncSession) -> str | None:
    """Return the role name for the user, e.g. 'owner', 'admin', 'member'."""
    if not user.role_id:
        return user.role  # fall back to the string column

    result = await db.execute(
        select(Role.name).where(Role.id == user.role_id)
    )
    row = result.scalar_one_or_none()
    return row


# ── require_permission() ──────────────────────────────────────────────────────

def require_permission(permission: str):
    """
    Dependency factory — checks that the authenticated user holds
    the given permission string (e.g. "users:delete", "billing:manage").
    Raises 403 if not.

    Usage:
        user: User = Depends(require_permission("billing:manage"))
    """

    async def dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        permissions = await _get_user_permissions(user, db)

        if permission not in permissions:
            raise ForbiddenException(
                detail=f"Permission denied — '{permission}' required"
            )

        return user

    return dependency


# ── require_role() ────────────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    Dependency factory — checks that the authenticated user has one
    of the given role names (e.g. "owner", "admin").
    Raises 403 if not.

    Usage:
        user: User = Depends(require_role("owner"))
        user: User = Depends(require_role("owner", "admin"))
    """

    async def dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        role_name = await _get_user_role_name(user, db)

        if role_name not in roles:
            raise ForbiddenException(
                detail=f"Role '{role_name}' is not permitted — "
                       f"required: {', '.join(roles)}"
            )

        return user

    return dependency


# ── Convenience shortcuts ─────────────────────────────────────────────────────

def owner_only():
    """Shortcut — only owner can access."""
    return require_role("owner")


def admin_or_owner():
    """Shortcut — admin or owner can access."""
    return require_role("admin", "owner")