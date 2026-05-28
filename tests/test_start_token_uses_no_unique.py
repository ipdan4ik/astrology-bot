from sqlalchemy import inspect

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


def test_start_token_uses_table_has_no_unique_index(engine):
    """Static check: table has no unique constraint involving account_id alone."""
    insp = inspect(engine.sync_engine)
    uniques = insp.get_unique_constraints("start_token_uses")
    for uc in uniques:
        assert uc["column_names"] != ["account_id"], (
            f"start_token_uses still has a UNIQUE(account_id): {uc}"
        )
