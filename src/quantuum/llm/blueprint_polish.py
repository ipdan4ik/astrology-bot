import asyncio
import re
from dataclasses import dataclass

from quantuum.astrology.sections import (
    BLUEPRINT_SECTION_ORDER,
    build_blueprint_context,
    build_reading_calc_md,
)
from quantuum.llm.reading_polish import polish_reading

# Map blueprint section keys → reading kinds for polishing.
_SECTION_TO_KIND = {
    "identity":     "astrology",
    "aspects":      "aspects",
    "vedic":        "vedic",
    "numerology":   "numerology",
    "bazi":         "bazi",
    "human_design": "human_design",
    "gene_keys":    "gene_keys",
    "mayan":        "mayan",
}

_FRAGMENT_RE = re.compile(
    r"<!-- field-overview-start -->\s*(.*?)\s*<!-- field-overview-end -->",
    re.DOTALL,
)


@dataclass
class _StitchedResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


def _strip_fragment(md: str) -> tuple[str, str | None]:
    m = _FRAGMENT_RE.search(md)
    if not m:
        return md, None
    frag = m.group(1).strip()
    cleaned = _FRAGMENT_RE.sub("", md).lstrip("\n")
    return cleaned, frag


def _opening_header(build_input) -> str:
    ctx = build_blueprint_context(build_input)
    return "\n".join([
        f"# {build_input.full_name} — QUANTUUM SOULMAP BLUEPRINT",
        "",
        f"_Birth: {build_input.birth_date} {build_input.birth_time} "
        f"({build_input.timezone}) · Place: "
        f"{build_input.birth_place if build_input.birth_place else '—'} · "
        f"Personal Year target: {ctx.for_year}_",
        "",
    ])


def _closing_template() -> str:
    return "\n".join([
        "",
        "## 🕊 ORACLE AFFIRMATION",
        "",
        "_I receive the codes the sky and the calendar wrote into me, and I answer with my life._",
        "",
        "## 🧭 CLOSING TRANSMISSION",
        "",
        "_Honour what is computed; embody what is true. The map is precise — your living of it is the medicine._",
        "",
    ])


async def polish_blueprint(client, calc_md: str, *, lang: str, model: str,
                            temperature: float, max_tokens: int, build_input):
    polished = await asyncio.gather(*[
        polish_reading(
            client, _SECTION_TO_KIND[section],
            build_reading_calc_md(section, build_input),
            lang=lang, model=model, temperature=temperature, max_tokens=max_tokens,
        )
        for section in BLUEPRINT_SECTION_ORDER
    ])

    fragments: list[str] = []
    bodies: list[str] = []
    total_in = total_out = 0
    last_model = model
    for r in polished:
        body, frag = _strip_fragment(r.text)
        if frag:
            fragments.append(frag)
        bodies.append(body)
        total_in += r.tokens_in or 0
        total_out += r.tokens_out or 0
        last_model = r.model

    parts: list[str] = [_opening_header(build_input)]
    parts.append("## 🌌 FIELD OVERVIEW\n")
    parts.append("| System | Code / Meaning |\n| --- | --- |")
    parts.extend(fragments if fragments else ["| (no field overview fragments emitted) |"])
    parts.append("")
    parts.extend(bodies)
    parts.append(_closing_template())

    return _StitchedResult(
        text="\n".join(parts),
        model=last_model,
        tokens_in=total_in,
        tokens_out=total_out,
    )
