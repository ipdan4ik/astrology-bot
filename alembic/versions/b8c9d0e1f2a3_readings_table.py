"""readings table

Revision ID: b8c9d0e1f2a3
Revises: c9d0e1f2a3b4
Create Date: 2026-05-26 10:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("natal_profile_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("calc_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_tokens_in", sa.Integer(), nullable=True),
        sa.Column("llm_tokens_out", sa.Integer(), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["natal_profile_id"], ["natal_profiles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_readings_account_id", "readings", ["account_id"])
    op.create_index("ix_readings_tenant_id", "readings", ["tenant_id"])
    op.create_index("ix_readings_tenant_created", "readings", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_readings_tenant_created", table_name="readings")
    op.drop_index("ix_readings_tenant_id", table_name="readings")
    op.drop_index("ix_readings_account_id", table_name="readings")
    op.drop_table("readings")
