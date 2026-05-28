from sqlalchemy import text

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import StartToken, StartTokenUse, Tenant


async def test_start_token_uses_has_no_unique_on_account(session):
    """After SP5 T1, two rows with the same account_id can coexist."""
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )

    session.add(StartToken(code="AAA00001", kind="referral", tenant_id=t.id,
                           owner_account_id=acc.id, status="active"))
    session.add(StartToken(code="BBB00002", kind="gift", tenant_id=t.id,
                           owner_account_id=acc.id, status="active"))
    await session.flush()
    session.add(StartTokenUse(token_code="AAA00001", account_id=acc.id))
    session.add(StartTokenUse(token_code="BBB00002", account_id=acc.id))
    await session.flush()  # must NOT raise IntegrityError


async def test_start_token_uses_table_has_no_unique_on_account(session):
    """Static check via information_schema: no UNIQUE(account_id) on the table."""
    rows = (
        await session.execute(
            text(
                """
                SELECT tc.constraint_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_name = 'start_token_uses'
                  AND tc.constraint_type = 'UNIQUE'
                """
            )
        )
    ).all()
    by_constraint: dict[str, list[str]] = {}
    for cname, col in rows:
        by_constraint.setdefault(cname, []).append(col)
    for cname, cols in by_constraint.items():
        assert cols != ["account_id"], (
            f"start_token_uses still has a UNIQUE(account_id): {cname}"
        )
