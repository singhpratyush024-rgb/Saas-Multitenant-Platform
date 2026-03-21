"""add_plans_and_stripe_fields

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-18 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── plans table ───────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("stripe_price_id", sa.String(), nullable=True),
        sa.Column("price_usd_cents", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("limits", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_plans_id", "plans", ["id"])
    op.create_index("ix_plans_key", "plans", ["key"], unique=True)

    # ── stripe fields on tenants ──────────────────────────────────
    op.add_column("tenants", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("stripe_subscription_id", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("stripe_subscription_status", sa.String(), nullable=True))

    op.create_index("ix_tenants_stripe_customer_id", "tenants", ["stripe_customer_id"], unique=True)
    op.create_index("ix_tenants_stripe_subscription_id", "tenants", ["stripe_subscription_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenants_stripe_subscription_id", table_name="tenants")
    op.drop_index("ix_tenants_stripe_customer_id", table_name="tenants")
    op.drop_column("tenants", "stripe_subscription_status")
    op.drop_column("tenants", "stripe_subscription_id")
    op.drop_column("tenants", "stripe_customer_id")
    op.drop_index("ix_plans_key", table_name="plans")
    op.drop_index("ix_plans_id", table_name="plans")
    op.drop_table("plans")