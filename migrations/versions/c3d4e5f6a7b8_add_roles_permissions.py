
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b8fb2a3166e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── 1. permissions ────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_permissions_id", "permissions", ["id"], unique=False)
    op.create_index("ix_permissions_name", "permissions", ["name"], unique=True)

    # ── 2. roles ──────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roles_id", "roles", ["id"], unique=False)

    # ── 3. role_permissions ───────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_id", "role_permissions", ["id"], unique=False)

    # ── 4. role_id FK on users ────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("role_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_role_id",
        "users", "roles",
        ["role_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:

    op.drop_constraint("fk_users_role_id", "users", type_="foreignkey")
    op.drop_column("users", "role_id")
    op.drop_index("ix_role_permissions_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_roles_id", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_permissions_name", table_name="permissions")
    op.drop_index("ix_permissions_id", table_name="permissions")
    op.drop_table("permissions")