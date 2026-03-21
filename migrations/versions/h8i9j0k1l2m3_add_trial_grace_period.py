"""add_trial_grace_period_to_tenants

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-03-21 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("grace_period_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenants_trial_ends_at", "tenants", ["trial_ends_at"])
    op.create_index("ix_tenants_grace_period_ends_at", "tenants", ["grace_period_ends_at"])


def downgrade() -> None:
    op.drop_index("ix_tenants_grace_period_ends_at", table_name="tenants")
    op.drop_index("ix_tenants_trial_ends_at", table_name="tenants")
    op.drop_column("tenants", "grace_period_ends_at")
    op.drop_column("tenants", "trial_ends_at")