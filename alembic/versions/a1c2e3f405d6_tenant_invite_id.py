"""tenants.invite_id link to onboarding invite

Revision ID: a1c2e3f405d6
Revises: f3a4b5c6d7e8
Create Date: 2026-06-03 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c2e3f405d6"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("invite_id", sa.Integer(), nullable=True),
    )
    op.create_index(op.f("ix_tenants_invite_id"), "tenants", ["invite_id"], unique=False)
    op.create_foreign_key(
        "fk_tenants_invite_id", "tenants", "tenant_invites", ["invite_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_tenants_invite_id", "tenants", type_="foreignkey")
    op.drop_index(op.f("ix_tenants_invite_id"), table_name="tenants")
    op.drop_column("tenants", "invite_id")
