"""payments + account billing: payment_providers, payments, account_subscriptions, account_packages

Revision ID: c2b3d4e5f6a7
Revises: b1a2c3d4e5f6
Create Date: 2026-05-21 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = "c2b3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("config_enc", sa.LargeBinary(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_providers_tenant_id"), "payment_providers", ["tenant_id"], unique=False)
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["payment_providers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_account_id"), "payments", ["account_id"], unique=False)
    op.create_index(op.f("ix_payments_external_id"), "payments", ["external_id"], unique=False)
    op.create_index(op.f("ix_payments_tenant_id"), "payments", ["tenant_id"], unique=False)
    op.create_table(
        "account_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_subscriptions_account_id"), "account_subscriptions", ["account_id"], unique=False)
    op.create_index(op.f("ix_account_subscriptions_tenant_id"), "account_subscriptions", ["tenant_id"], unique=False)
    op.create_index(
        "uq_active_subscription_per_plan",
        "account_subscriptions",
        ["account_id", "plan_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active','grace')"),
    )
    op.create_table(
        "account_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("requests_remaining", sa.Integer(), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["package_plans.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_packages_account_id"), "account_packages", ["account_id"], unique=False)
    op.create_index(op.f("ix_account_packages_tenant_id"), "account_packages", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_account_packages_tenant_id"), table_name="account_packages")
    op.drop_index(op.f("ix_account_packages_account_id"), table_name="account_packages")
    op.drop_table("account_packages")
    op.drop_index("uq_active_subscription_per_plan", table_name="account_subscriptions")
    op.drop_index(op.f("ix_account_subscriptions_tenant_id"), table_name="account_subscriptions")
    op.drop_index(op.f("ix_account_subscriptions_account_id"), table_name="account_subscriptions")
    op.drop_table("account_subscriptions")
    op.drop_index(op.f("ix_payments_tenant_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_external_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_account_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_payment_providers_tenant_id"), table_name="payment_providers")
    op.drop_table("payment_providers")
