def test_create_master_dispatcher_has_onboarding_and_owner_console_routers():
    from quantuum.bot.handlers import master_onboarding, owner_console
    from quantuum.bot.master_app import create_master_dispatcher

    # NOTE: handler routers are module-level singletons, so create_master_dispatcher()
    # must be called exactly once per process (it is, in production). Build it once here
    # and assert everything against that single dispatcher.
    dp = create_master_dispatcher()
    # The onboarding router must be attached; astrology routers must not be.
    # Handlers live in sub-routers when registered via include_router().
    observers = [h for r in dp.sub_routers for h in r.message.handlers]
    assert observers  # has message handlers
    # Sanity: dispatcher builds without error and has a callback_query observer too
    assert dp.callback_query is not None
    # Both the onboarding and owner self-service console routers are registered.
    assert master_onboarding.router in dp.sub_routers
    assert owner_console.router in dp.sub_routers
    assert len(dp.sub_routers) >= 2
