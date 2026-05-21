from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "blueprint_writer.txt"


async def polish_blueprint(client, calc_md, *, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Transform this calculated Markdown into the final premium Quantuum SoulMap Blueprint.",
            "",
            "CALCULATED MARKDOWN:",
            calc_md,
        ]
    )
    return await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
