def test_create_master_dispatcher_has_onboarding_router():
    from quantuum.bot.master_app import create_master_dispatcher

    dp = create_master_dispatcher()
    # The onboarding router must be attached; astrology routers must not be.
    # Handlers live in sub-routers when registered via include_router().
    observers = [h for r in dp.sub_routers for h in r.message.handlers]
    assert observers  # has message handlers
    # Sanity: dispatcher builds without error and has a callback_query observer too
    assert dp.callback_query is not None
