from pathlib import Path

_PROMPTS = Path(__file__).parent / "prompts"

READING_PROMPTS: dict[str, Path] = {
    "bazi":         _PROMPTS / "reading_bazi.txt",
    "numerology":   _PROMPTS / "reading_numerology.txt",
    "human_design": _PROMPTS / "reading_human_design.txt",
    "astrology":    _PROMPTS / "reading_astrology.txt",
    "vedic":        _PROMPTS / "reading_vedic.txt",
    "gene_keys":    _PROMPTS / "reading_gene_keys.txt",
    "mayan":        _PROMPTS / "reading_mayan.txt",
    "aspects":      _PROMPTS / "reading_aspects.txt",
}


_KIND_LABEL: dict[str, str] = {
    "bazi": "BaZi (Chinese Four Pillars)",
    "numerology": "Pythagorean Numerology",
    "human_design": "Human Design",
    "astrology": "Western Tropical Astrology",
    "vedic": "Vedic (Sidereal) Astrology",
    "gene_keys": "Gene Keys",
    "mayan": "Mayan Tzolkin",
    "aspects": "Natal Aspects",
}


async def polish_reading(client, kind: str, calc_md: str, *, lang: str,
                         model: str, temperature: float, max_tokens: int):
    if kind not in READING_PROMPTS:
        raise KeyError(f"unknown reading kind: {kind}")
    system = READING_PROMPTS[kind].read_text()
    label = _KIND_LABEL[kind]
    user = "\n".join([
        f"Transform this calculated {label} chart slice into the polished Quantuum reading.",
        f"Answer in language: {lang}.",
        "",
        "CALCULATED MARKDOWN:",
        calc_md,
    ])
    return await client.complete(
        system=system, user=user,
        model=model, temperature=temperature, max_tokens=max_tokens,
    )
