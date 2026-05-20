from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.domain.invites import (
    create_invite,
    get_invite_by_code,
    invite_is_usable,
    list_invites,
    revoke_invite,
)


async def test_create_and_get_invite(session):
    inv = await create_invite(session, created_by_account_id=None, tier="vip", max_uses=2)
    assert inv.code
    assert inv.tier == "vip"
    fetched = await get_invite_by_code(session, inv.code)
    assert fetched is not None and fetched.id == inv.id


async def test_list_invites_newest_first(session):
    a = await create_invite(session, created_by_account_id=None)
    b = await create_invite(session, created_by_account_id=None)
    rows = await list_invites(session)
    assert [r.id for r in rows][:2] == [b.id, a.id]


async def test_revoke_invite(session):
    inv = await create_invite(session, created_by_account_id=None)
    revoked = await revoke_invite(session, inv.id)
    assert revoked.status == "revoked"
    assert await revoke_invite(session, 999999) is None


def test_invite_is_usable():
    now = utcnow()
    active = type("I", (), {"status": "active", "expires_at": None, "used_count": 0, "max_uses": 1})()
    assert invite_is_usable(active, now=now) is True

    expired = type("I", (), {"status": "active", "expires_at": now - timedelta(hours=1), "used_count": 0, "max_uses": 1})()
    assert invite_is_usable(expired, now=now) is False

    exhausted = type("I", (), {"status": "active", "expires_at": None, "used_count": 1, "max_uses": 1})()
    assert invite_is_usable(exhausted, now=now) is False

    revoked = type("I", (), {"status": "revoked", "expires_at": None, "used_count": 0, "max_uses": 1})()
    assert invite_is_usable(revoked, now=now) is False
