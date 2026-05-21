"""daily_subscriptions + daily_horoscopes

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-21 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_subscriptions",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("send_hour", sa.Integer(), nullable=False),
        sa.Column("last_sent_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_index("ix_daily_subscriptions_tenant_id", "daily_subscriptions", ["tenant_id"])

    op.create_table(
        "daily_horoscopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("natal_profile_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("transit_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("horoscope_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_tokens_in", sa.Integer(), nullable=True),
        sa.Column("llm_tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["natal_profile_id"], ["natal_profiles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "local_date", name="uq_daily_horoscope_account_date"),
    )
    op.create_index("ix_daily_horoscopes_account_id", "daily_horoscopes", ["account_id"])
    op.create_index("ix_daily_horoscopes_tenant_id", "daily_horoscopes", ["tenant_id"])
    op.create_index("ix_daily_horoscopes_tenant_created", "daily_horoscopes", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_daily_horoscopes_tenant_created", table_name="daily_horoscopes")
    op.drop_index("ix_daily_horoscopes_tenant_id", table_name="daily_horoscopes")
    op.drop_index("ix_daily_horoscopes_account_id", table_name="daily_horoscopes")
    op.drop_table("daily_horoscopes")
    op.drop_index("ix_daily_subscriptions_tenant_id", table_name="daily_subscriptions")
    op.drop_table("daily_subscriptions")
