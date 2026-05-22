from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "qa_astrologer.txt"


async def qa_answer(client, calc_md, question, *, lang, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Answer the user's question using only the calculated chart below.",
            f"Answer in language: {lang}.",
            "",
            "CALCULATED CHART:",
            calc_md,
            "",
            "QUESTION:",
            question,
        ]
    )
    return await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
