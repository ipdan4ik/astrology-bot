from quantuum.db.bootstrap import force_update_strings
from quantuum.db.models import PlatformString
from quantuum.i18n.seed_strings import BASE_STRINGS


async def test_force_update_strings_overwrites_stale(session):
    # seed a STALE value for an existing key
    session.add(PlatformString(key="btn.generate", lang="en", text="OLD VALUE"))
    await session.commit()

    await force_update_strings(session, ["btn.generate"])

    row = await session.get(PlatformString, ("btn.generate", "en"))
    await session.refresh(row)
    assert row.text == BASE_STRINGS["btn.generate"]["en"]  # updated to current
    assert row.text != "OLD VALUE"


async def test_force_update_strings_inserts_missing(session):
    # key absent → helper inserts it from BASE_STRINGS
    assert await session.get(PlatformString, ("help.text", "en")) is None

    await force_update_strings(session, ["help.text"])

    row = await session.get(PlatformString, ("help.text", "en"))
    assert row is not None
    assert row.text == BASE_STRINGS["help.text"]["en"]
