"""subscription active-sub unique index: include tenant_id

Revision ID: f3a4b5c6d7e8
Revises: 30bed95a2812
Create Date: 2026-06-03 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "30bed95a2812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "uq_active_subscription_per_plan", table_name="account_subscriptions"
    )
    op.create_index(
        "uq_active_subscription_per_plan",
        "account_subscriptions",
        ["tenant_id", "account_id", "plan_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active','grace')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_subscription_per_plan", table_name="account_subscriptions"
    )
    op.create_index(
        "uq_active_subscription_per_plan",
        "account_subscriptions",
        ["account_id", "plan_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active','grace')"),
    )
