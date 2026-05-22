from quantuum.db.models import Account, AccountIdentity


async def _make_superadmin(session, *, tg=None):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    if tg is not None:
        session.add(
            AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg)
        )
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_find_superadmin_by_tg_returns_superadmin(session):
    from quantuum.auth.identity import find_superadmin_by_tg

    acc = await _make_superadmin(session, tg="555")
    found = await find_superadmin_by_tg(session, "555")
    assert found is not None
    assert found.id == acc.id
    assert found.is_superadmin is True


async def test_find_superadmin_by_tg_ignores_platform_dup(session):
    """A non-superadmin account sharing the same tg id must not be returned."""
    from quantuum.auth.identity import find_superadmin_by_tg

    sa = await _make_superadmin(session, tg="777")
    plain = Account(tenant_id=None, is_superadmin=False)
    session.add(plain)
    await session.flush()
    session.add(AccountIdentity(account_id=plain.id, provider="tg_chat", provider_user_id="777"))
    await session.commit()

    found = await find_superadmin_by_tg(session, "777")
    assert found is not None
    assert found.id == sa.id  # the superadmin, not the plain account


async def test_find_superadmin_by_tg_none_for_unknown(session):
    from quantuum.auth.identity import find_superadmin_by_tg

    assert await find_superadmin_by_tg(session, "404404") is None


async def test_ensure_superadmin_links_tg_idempotently(session, monkeypatch):
    from quantuum.db import bootstrap as bs
    from quantuum.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_TG_ID", "12321")
    get_settings.cache_clear()

    # First run: creates account + magic_link + tg_chat identity.
    await bs.ensure_superadmin(session)
    # Second run: must NOT create a duplicate tg_chat identity.
    await bs.ensure_superadmin(session)

    from quantuum.auth.identity import find_superadmin_by_tg

    sa = await find_superadmin_by_tg(session, "12321")
    assert sa is not None and sa.is_superadmin is True

    from sqlmodel import select as _select
    from quantuum.db.models import AccountIdentity as _AI

    rows = (
        await session.execute(
            _select(_AI).where(_AI.provider == "tg_chat", _AI.provider_user_id == "12321")
        )
    ).scalars().all()
    assert len(rows) == 1  # idempotent

    get_settings.cache_clear()
