"""qa_answers table

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-05-21 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("natal_profile_id", sa.Integer(), nullable=False),
        sa.Column("blueprint_id", sa.Integer(), nullable=True),
        sa.Column("question", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("answer_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
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
    op.create_index("ix_qa_answers_account_id", "qa_answers", ["account_id"])
    op.create_index("ix_qa_answers_tenant_id", "qa_answers", ["tenant_id"])
    op.create_index("ix_qa_answers_tenant_created", "qa_answers", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_qa_answers_tenant_created", table_name="qa_answers")
    op.drop_index("ix_qa_answers_tenant_id", table_name="qa_answers")
    op.drop_index("ix_qa_answers_account_id", table_name="qa_answers")
    op.drop_table("qa_answers")
