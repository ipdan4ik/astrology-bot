from quantuum.bot.ui.callbacks import LangCb


def _inline(markup):
    return [b for row in markup.inline_keyboard for b in row]


async def test_picker_lists_enabled_langs_default_first(session, default_tenant):
    # Seed ru (default) + en for the tenant.
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.keyboards import language_picker_kb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()

    markup = await language_picker_kb(default_tenant.id, action="setup")
    buttons = _inline(markup)

    labels = [b.text for b in buttons]
    assert labels == ["🇷🇺 Русский", "🇬🇧 English"]  # default (ru) first, then sorted

    codes = [LangCb.unpack(b.callback_data).lang for b in buttons]
    assert codes == ["ru", "en"]
    actions = {LangCb.unpack(b.callback_data).action for b in buttons}
    assert actions == {"setup"}


async def test_picker_uses_action(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.keyboards import language_picker_kb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()

    markup = await language_picker_kb(default_tenant.id, action="set")
    actions = {LangCb.unpack(b.callback_data).action for b in _inline(markup)}
    assert actions == {"set"}


def test_lang_labels_cover_all_platform_langs():
    from quantuum.bot.ui.keyboards import LANG_LABELS
    from quantuum.i18n.langs import PLATFORM_LANGS

    for code in PLATFORM_LANGS:
        assert code in LANG_LABELS, f"LANG_LABELS missing native name for {code!r}"
        assert LANG_LABELS[code].strip(), f"LANG_LABELS[{code!r}] is empty"
