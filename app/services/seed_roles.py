
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.role import Role
from app.models.permission import Permission, RolePermission


ALL_PERMISSIONS: list[tuple[str, str]] = [
    # (name,                  description)
    ("users:read",            "View users in the tenant"),
    ("users:write",           "Create and update users"),
    ("users:delete",          "Delete users"),
    ("projects:read",         "View projects"),
    ("projects:write",        "Create and update projects"),
    ("projects:delete",       "Delete projects"),
    ("billing:read",          "View billing information"),
    ("billing:manage",        "Manage billing and subscriptions"),
    ("roles:read",            "View roles and permissions"),
    ("roles:manage",          "Create, update and delete roles"),
    ("tenant:manage",         "Manage tenant settings"),
]

# ── Per-role permission sets ──────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": [
        # Full access — everything
        "users:read", "users:write", "users:delete",
        "projects:read", "projects:write", "projects:delete",
        "billing:read", "billing:manage",
        "roles:read", "roles:manage",
        "tenant:manage",
    ],
    "admin": [
        # Manage users and projects, read billing, no tenant/role management
        "users:read", "users:write", "users:delete",
        "projects:read", "projects:write", "projects:delete",
        "billing:read",
        "roles:read",
    ],
    "member": [
        # Read-only on most things, write own projects
        "users:read",
        "projects:read", "projects:write",
    ],
}

# "member" is the role auto-assigned to new registrations
DEFAULT_ROLE_NAME = "member"



async def seed_default_roles(db: AsyncSession, tenant_id: int) -> None:
    """
    Idempotent — safe to call multiple times on the same tenant.
    Creates all Permission rows (global, once), then creates the
    three Role rows for this tenant and wires up RolePermission rows.
    """

    # 1. Ensure every permission exists (global table, shared across tenants)
    permission_map: dict[str, Permission] = {}

    for perm_name, perm_desc in ALL_PERMISSIONS:
        result = await db.execute(
            select(Permission).where(Permission.name == perm_name)
        )
        perm = result.scalar_one_or_none()

        if not perm:
            perm = Permission(name=perm_name, description=perm_desc)
            db.add(perm)
            await db.flush()   # get perm.id without committing

        permission_map[perm_name] = perm

    # 2. Create roles for this tenant
    for role_name, perm_names in ROLE_PERMISSIONS.items():

        # Skip if role already exists for this tenant (idempotent)
        result = await db.execute(
            select(Role).where(
                Role.name == role_name,
                Role.tenant_id == tenant_id,
            )
        )
        role = result.scalar_one_or_none()

        if not role:
            role = Role(
                name=role_name,
                tenant_id=tenant_id,
                is_default=(role_name == DEFAULT_ROLE_NAME),
            )
            db.add(role)
            await db.flush()   # get role.id

        # 3. Wire permissions to role (skip duplicates)
        for perm_name in perm_names:
            perm = permission_map[perm_name]

            result = await db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if not result.scalar_one_or_none():
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    await db.commit()