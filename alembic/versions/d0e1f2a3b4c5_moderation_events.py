"""moderation_events table

Revision ID: d0e1f2a3b4c5
Revises: b8c9d0e1f2a3
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=True),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("text_preview", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_moderation_events_account_id", "moderation_events", ["account_id"])
    op.create_index("ix_moderation_events_tenant_id", "moderation_events", ["tenant_id"])
    op.create_index("ix_moderation_events_created_at", "moderation_events", ["created_at"])
    op.create_index(
        "ix_moderation_events_category_created",
        "moderation_events",
        ["category", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_events_category_created", table_name="moderation_events")
    op.drop_index("ix_moderation_events_created_at", table_name="moderation_events")
    op.drop_index("ix_moderation_events_tenant_id", table_name="moderation_events")
    op.drop_index("ix_moderation_events_account_id", table_name="moderation_events")
    op.drop_table("moderation_events")
