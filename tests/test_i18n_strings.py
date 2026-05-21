import pytest

from quantuum.db.models import PlatformString, TenantStringOverride, TenantLanguage
from quantuum.i18n.strings import (
    load_platform_strings,
    load_tenant_overrides,
    merged_strings,
    get_tenant_default_lang,
    get_enabled_langs,
)


async def _seed(session, tid):
    session.add(PlatformString(key="hi", lang="en", text="Hello"))
    session.add(PlatformString(key="bye", lang="en", text="Bye"))
    session.add(TenantStringOverride(tenant_id=tid, key="hi", lang="en", text="Hey"))
    session.add(TenantLanguage(tenant_id=tid, lang="en", enabled=True, is_default=True))
    session.add(TenantLanguage(tenant_id=tid, lang="de", enabled=False, is_default=False))
    await session.commit()


@pytest.mark.asyncio
async def test_merged_overlays_override(session, default_tenant):
    await _seed(session, default_tenant.id)
    merged = await merged_strings(session, default_tenant.id, "en")
    assert merged["hi"] == "Hey"      # override wins
    assert merged["bye"] == "Bye"     # platform fallback


@pytest.mark.asyncio
async def test_platform_and_overrides(session, default_tenant):
    await _seed(session, default_tenant.id)
    assert (await load_platform_strings(session, "en"))["hi"] == "Hello"
    assert (await load_tenant_overrides(session, default_tenant.id, "en")) == {"hi": "Hey"}


@pytest.mark.asyncio
async def test_default_and_enabled_langs(session, default_tenant):
    await _seed(session, default_tenant.id)
    assert await get_tenant_default_lang(session, default_tenant.id) == "en"
    assert await get_enabled_langs(session, default_tenant.id) == {"en"}
