from quantuum.divination import iching, tarot


def build_divination_calc_md(kind: str, draw: dict | None) -> str:
    """Dispatch divination calc_md builders by kind."""
    if draw is None:
        raise ValueError(f"divination kind {kind!r} requires draw_jsonb")
    if kind == "tarot":
        return tarot.build_calc_md_from_jsonb(draw)
    if kind == "iching":
        return iching.build_calc_md_from_jsonb(draw)
    raise ValueError(f"not a divination kind: {kind!r}")
