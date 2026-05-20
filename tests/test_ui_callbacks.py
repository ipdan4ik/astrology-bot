from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, OnboardCb, ProfileCb


def test_profile_cb_roundtrip():
    cb = ProfileCb(action="edit", field="birth_time")
    assert ProfileCb.unpack(cb.pack()) == cb


def test_history_cb_roundtrip():
    assert HistoryCb.unpack(HistoryCb(action="page", page=2).pack()) == HistoryCb(action="page", page=2)
    assert HistoryCb.unpack(HistoryCb(action="open", bp_id=7).pack()) == HistoryCb(action="open", bp_id=7)


def test_blueprint_and_onboard_cb_roundtrip():
    assert BlueprintCb.unpack(BlueprintCb(action="download", bp_id=3).pack()) == BlueprintCb(action="download", bp_id=3)
    assert OnboardCb.unpack(OnboardCb(action="cancel").pack()) == OnboardCb(action="cancel")
