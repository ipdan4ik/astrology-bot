from quantuum.bot.ui.paging import page_slice


def test_page_slice_has_next_when_overfetched():
    rows, has_next = page_slice([1, 2, 3, 4, 5, 6], size=5)
    assert rows == [1, 2, 3, 4, 5]
    assert has_next is True


def test_page_slice_no_next_when_exact_or_less():
    assert page_slice([1, 2, 3], size=5) == ([1, 2, 3], False)
    assert page_slice([1, 2, 3, 4, 5], size=5) == ([1, 2, 3, 4, 5], False)


def test_page_slice_empty():
    assert page_slice([], size=5) == ([], False)
