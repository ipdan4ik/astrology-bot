from quantuum.bot.handlers.master_onboarding import slug_is_available


async def test_slug_is_available(session, default_tenant):
    assert await slug_is_available(session, "brand-new") is True
    assert await slug_is_available(session, "default") is False


def test_owner_onboard_callback_roundtrip():
    from quantuum.bot.ui.callbacks import OwnerOnboardCb

    packed = OwnerOnboardCb(action="confirm").pack()
    assert OwnerOnboardCb.unpack(packed).action == "confirm"
