from unittest.mock import AsyncMock

from quantuum.tasks.daily import daily_dispatch


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, s):
        self._s = s

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


async def test_daily_dispatch_enqueues_due_accounts(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    async def fake_due(_session, *, now):
        return [101, 202]

    spy = AsyncMock()
    monkeypatch.setattr(daily_mod, "due_daily_account_ids", fake_due)
    monkeypatch.setattr(daily_mod, "enqueue_daily", spy)

    await daily_dispatch({"sessionmaker": _Maker(session)})

    assert spy.await_count == 2
    assert [c.args[0] for c in spy.await_args_list] == [101, 202]


async def test_daily_dispatch_no_due_enqueues_nothing(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    async def fake_due(_session, *, now):
        return []

    spy = AsyncMock()
    monkeypatch.setattr(daily_mod, "due_daily_account_ids", fake_due)
    monkeypatch.setattr(daily_mod, "enqueue_daily", spy)

    await daily_dispatch({"sessionmaker": _Maker(session)})
    spy.assert_not_awaited()
