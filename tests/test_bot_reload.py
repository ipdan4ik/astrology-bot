import pytest

from quantuum.bot.reload import BotSpec, diff_specs


def _spec(bot_id: int, is_master: bool = False) -> BotSpec:
    return BotSpec(bot_telegram_id=bot_id, token=f"{bot_id}:tok", is_master=is_master)


@pytest.mark.no_db
def test_diff_specs_adds_new():
    desired = {1: _spec(1), 2: _spec(2)}
    assert diff_specs({1}, desired) == ({2}, set())


@pytest.mark.no_db
def test_diff_specs_removes_missing():
    desired = {1: _spec(1)}
    assert diff_specs({1, 3}, desired) == (set(), {3})


@pytest.mark.no_db
def test_diff_specs_mixed_and_noop():
    desired = {1: _spec(1), 2: _spec(2)}
    assert diff_specs({2, 3}, desired) == ({1}, {3})
    assert diff_specs({1, 2}, desired) == (set(), set())
