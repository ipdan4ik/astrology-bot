"""plan catalog: subscription_plans, package_plans

Revision ID: b1a2c3d4e5f6
Revises: a2b1c0d9e8f7
Create Date: 2026-05-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "a2b1c0d9e8f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscription_plans_slug"), "subscription_plans", ["slug"], unique=False)
    op.create_index(op.f("ix_subscription_plans_tenant_id"), "subscription_plans", ["tenant_id"], unique=False)
    op.create_table(
        "package_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_after_days", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_package_plans_slug"), "package_plans", ["slug"], unique=False)
    op.create_index(op.f("ix_package_plans_tenant_id"), "package_plans", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_package_plans_tenant_id"), table_name="package_plans")
    op.drop_index(op.f("ix_package_plans_slug"), table_name="package_plans")
    op.drop_table("package_plans")
    op.drop_index(op.f("ix_subscription_plans_tenant_id"), table_name="subscription_plans")
    op.drop_index(op.f("ix_subscription_plans_slug"), table_name="subscription_plans")
    op.drop_table("subscription_plans")
