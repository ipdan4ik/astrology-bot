from pathlib import Path

from quantuum.llm.lang_instruction import lang_instruction

PROMPT_PATH = Path(__file__).parent / "prompts" / "daily_astrologer.txt"


async def daily_horoscope(client, natal_md, transit_md, *, lang, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Write today's short horoscope for this person using ONLY the natal chart and the transit table below.",
            lang_instruction(lang),
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
