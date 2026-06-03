"""tenant_bots.webhook_secret_token

Revision ID: b2d3f4a5c607
Revises: a1c2e3f405d6
Create Date: 2026-06-03 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2d3f4a5c607"
down_revision: Union[str, Sequence[str], None] = "a1c2e3f405d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_bots",
        sa.Column("webhook_secret_token", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_bots", "webhook_secret_token")
