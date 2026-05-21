"""i18n tables: platform_config, tenant_config, platform_strings, tenant_string_overrides, tenant_languages

Revision ID: f5e6a7b8c9d0
Revises: e4d5f6a7b8c9
Create Date: 2026-05-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

revision: str = "f5e6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "e4d5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_config",
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_account_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "tenant_config",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_account_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["updated_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("tenant_id", "key"),
    )
    op.create_table(
        "platform_strings",
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("key", "lang"),
    )
    op.create_table(
        "tenant_string_overrides",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_account_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["updated_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("tenant_id", "key", "lang"),
    )
    op.create_table(
        "tenant_languages",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("tenant_id", "lang"),
    )
    op.create_index(
        "uq_tenant_default_language",
        "tenant_languages",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_tenant_default_language", table_name="tenant_languages")
    op.drop_table("tenant_languages")
    op.drop_table("tenant_string_overrides")
    op.drop_table("platform_strings")
    op.drop_table("tenant_config")
    op.drop_table("platform_config")
