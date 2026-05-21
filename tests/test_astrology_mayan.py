from datetime import datetime, timezone

from quantuum.astrology.mayan import tzolkin

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)


def test_anna_tzolkin_matches_golden():
    tz = tzolkin(ANNA)
    assert tz.trecena == 5
    assert tz.sign_name == "Eb"
    assert tz.dreamspell_name == "Yellow Human"
    assert tz.full == "5 Eb"
    assert tz.kin == 252
