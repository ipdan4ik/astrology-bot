from quantuum.i18n import Translator


async def append_signature(body: str, *, tenant_id: int, lang: str) -> str:
    """Append brand.signature on a blank line. No-op when resolved value is empty.

    Resolves via the standard Translator (default empty string), so platform
    base + tenant override merging is handled by the existing i18n stack.
    """
    translator = Translator(tenant_id=tenant_id, lang=lang)
    raw = await translator("brand.signature", default="")
    sig = raw.strip()
    if not sig:
        return body
    return f"{body}\n\n{sig}"
