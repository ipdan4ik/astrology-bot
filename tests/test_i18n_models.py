import pytest
from sqlalchemy.exc import IntegrityError
from quantuum.db.models import PlatformString, TenantLanguage


async def test_platform_string_roundtrip(session):
    session.add(PlatformString(key="greet", lang="en", text="Hello"))
    await session.commit()
    got = await session.get(PlatformString, ("greet", "en"))
    assert got.text == "Hello"


async def test_one_default_language_per_tenant(session, default_tenant):
    session.add(TenantLanguage(tenant_id=default_tenant.id, lang="ru", enabled=True, is_default=True))
    await session.commit()
    session.add(TenantLanguage(tenant_id=default_tenant.id, lang="en", enabled=True, is_default=True))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
