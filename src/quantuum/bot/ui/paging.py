def page_slice(window: list, size: int) -> tuple[list, bool]:
    """Given a window of up to size+1 rows fetched for one page, return the
    page's rows (capped at size) and whether a next page exists."""
    return window[:size], len(window) > size
