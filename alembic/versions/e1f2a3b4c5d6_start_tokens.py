"""start_tokens

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-05-27 23:27:35.058724

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "start_tokens",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner_account_id", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["owner_account_id"], ["accounts.id"]),
    )
    op.create_index("ix_start_tokens_kind", "start_tokens", ["kind"])
    op.create_index("ix_start_tokens_tenant_id", "start_tokens", ["tenant_id"])
    op.create_index("ix_start_tokens_owner_account_id", "start_tokens", ["owner_account_id"])

    op.create_table(
        "start_token_uses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_code", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["token_code"], ["start_tokens.code"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("account_id", name="uq_start_token_uses_account_id"),
    )
    op.create_index("ix_start_token_uses_token_code", "start_token_uses", ["token_code"])


def downgrade() -> None:
    op.drop_index("ix_start_token_uses_token_code", table_name="start_token_uses")
    op.drop_table("start_token_uses")
    op.drop_index("ix_start_tokens_owner_account_id", table_name="start_tokens")
    op.drop_index("ix_start_tokens_tenant_id", table_name="start_tokens")
    op.drop_index("ix_start_tokens_kind", table_name="start_tokens")
    op.drop_table("start_tokens")
