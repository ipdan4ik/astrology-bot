"""drop start_token_uses unique account_id

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-28 00:00:00.000000
"""
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_start_token_uses_account_id",
        "start_token_uses",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_start_token_uses_account_id",
        "start_token_uses",
        ["account_id"],
    )
