"""account_packages source backfill

Revision ID: 30bed95a2812
Revises: a3b4c5d6e7f8
Create Date: 2026-06-03 19:09:49.257166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '30bed95a2812'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. source column (default 'purchase' for existing purchase rows)
    op.add_column(
        "account_packages",
        sa.Column("source", sa.String(), nullable=False, server_default="purchase"),
    )
    # 2. plan_id becomes nullable (gifts/referrals/welcome have no plan)
    op.alter_column("account_packages", "plan_id", existing_type=sa.Integer(), nullable=True)

    # 3. Backfill: for any balance whose counter exceeds its valid ledger sum,
    #    insert one compensating ledger row for the difference so the first
    #    recompute after deploy does not wipe gift/referral/welcome credits.
    op.execute(
        """
        INSERT INTO account_packages
            (tenant_id, account_id, plan_id, source, requests_remaining,
             purchased_at, expires_at, payment_id, created_at)
        SELECT a.tenant_id,
               b.account_id,
               NULL,
               'backfill',
               b.package_credits - COALESCE(led.valid_sum, 0),
               now(), NULL, NULL, now()
        FROM account_balance b
        JOIN accounts a ON a.id = b.account_id
        LEFT JOIN (
            SELECT account_id, SUM(requests_remaining) AS valid_sum
            FROM account_packages
            WHERE requests_remaining > 0
              AND (expires_at IS NULL OR expires_at > now())
            GROUP BY account_id
        ) led ON led.account_id = b.account_id
        WHERE b.package_credits > COALESCE(led.valid_sum, 0)
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM account_packages WHERE source = 'backfill'")
    op.alter_column("account_packages", "plan_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("account_packages", "source")
