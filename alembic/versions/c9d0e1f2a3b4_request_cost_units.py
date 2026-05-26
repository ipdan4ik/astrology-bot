"""ensure requests.cost_units default

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2
Create Date: 2026-05-26 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "requests",
        "cost_units",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="1",
    )
    op.execute("UPDATE requests SET cost_units = 1 WHERE cost_units IS NULL")


def downgrade() -> None:
    op.alter_column(
        "requests",
        "cost_units",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )
