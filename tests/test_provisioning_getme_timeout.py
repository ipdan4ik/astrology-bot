import asyncio

import quantuum.domain.provisioning as prov


class _HangingBot:
    async def get_me(self):
        await asyncio.sleep(5)
        return object()


async def test_master_can_manage_bots_times_out(monkeypatch):
    monkeypatch.setattr(prov, "GETME_TIMEOUT_S", 0.01)
    result = await prov.master_can_manage_bots(_HangingBot())
    assert result is False
