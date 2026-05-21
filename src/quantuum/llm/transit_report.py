from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "transit_astrologer.txt"


async def transit_report(client, natal_md, transit_md, *, lang, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Write a transit reading for this person using ONLY the natal chart and the computed transit tables below.",
            f"Answer in language: {lang}.",
            "",
            "NATAL CHART:",
            natal_md,
            "",
            "TRANSITS:",
            transit_md,
        ]
    )
    return await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
