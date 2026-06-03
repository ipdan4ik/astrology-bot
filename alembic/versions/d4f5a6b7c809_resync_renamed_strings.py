"""resync renamed i18n keys onto seeded DBs

Revision ID: d4f5a6b7c809
Revises: c3e4f5a6b708
Create Date: 2026-06-04 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f5a6b7c809"
down_revision: Union[str, Sequence[str], None] = "c3e4f5a6b708"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from quantuum.i18n.seed_strings import BASE_STRINGS, RESYNC_KEYS

    conn = op.get_bind()
    for key in RESYNC_KEYS:
        for lang, text in BASE_STRINGS.get(key, {}).items():
            conn.execute(
                sa.text(
                    "UPDATE platform_strings SET text = :t WHERE key = :k AND lang = :l"
                ),
                {"t": text, "k": key, "l": lang},
            )


def downgrade() -> None:
    # Text-only data migration; no-op down (old text is not retained).
    pass
