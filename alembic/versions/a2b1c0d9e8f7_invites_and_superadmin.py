"""invites table + accounts superadmin/nullable tenant_id

Revision ID: a2b1c0d9e8f7
Revises: 333649f38ecf
Create Date: 2026-05-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "a2b1c0d9e8f7"
down_revision: Union[str, Sequence[str], None] = "333649f38ecf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("tier", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("preset_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("preset_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("preset_username", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("preset_default_lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_invites_code"), "tenant_invites", ["code"], unique=True)
    op.add_column(
        "accounts",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.alter_column("accounts", "tenant_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("accounts", "tenant_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("accounts", "is_superadmin")
    op.drop_index(op.f("ix_tenant_invites_code"), table_name="tenant_invites")
    op.drop_table("tenant_invites")
