"""payouts unique (tenant_id, period_start, period_end)

Revision ID: c3e4f5a6b708
Revises: b2d3f4a5c607
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3e4f5a6b708"
down_revision: Union[str, Sequence[str], None] = "b2d3f4a5c607"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_payout_tenant_period", "payouts",
        ["tenant_id", "period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_payout_tenant_period", "payouts", type_="unique")
