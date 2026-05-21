"""transit_reports table

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-21 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transit_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("natal_profile_id", sa.Integer(), nullable=False),
        sa.Column("blueprint_id", sa.Integer(), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("transit_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("report_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
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
        sa.ForeignKeyConstraint(["blueprint_id"], ["blueprints.id"]),
        sa.ForeignKeyConstraint(["natal_profile_id"], ["natal_profiles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transit_reports_account_id", "transit_reports", ["account_id"])
    op.create_index("ix_transit_reports_tenant_id", "transit_reports", ["tenant_id"])
    op.create_index("ix_transit_reports_tenant_created", "transit_reports", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_transit_reports_tenant_created", table_name="transit_reports")
    op.drop_index("ix_transit_reports_tenant_id", table_name="transit_reports")
    op.drop_index("ix_transit_reports_account_id", table_name="transit_reports")
    op.drop_table("transit_reports")
