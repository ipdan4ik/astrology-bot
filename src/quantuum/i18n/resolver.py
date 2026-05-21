from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.i18n.strings import get_tenant_default_lang, merged_strings
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def safe_format(template: str, vars: dict) -> str:
    """Format *template* with *vars*, leaving any missing placeholders intact."""
    return template.format_map(_SafeDict(vars))


async def t(
    session: AsyncSession,
    key: str,
    lang: str,
    *,
    tenant_id: int,
    default: str | None = None,
    **vars,
) -> str:
    """Resolve a translation key using the 6-step fallback chain.

    Steps:
      1+2. Tenant override then platform string for *lang*.
      3+4. Same lookup for the tenant default lang (if different from *lang*).
        5. The *default* argument (if provided), formatted with **vars.
        6. A ``[missing: key]`` sentinel with a warning log.
    """
    default_lang = await get_tenant_default_lang(session, tenant_id)

    # Steps 1 & 2: merged (override-over-platform) for the requested lang
    primary = await merged_strings(session, tenant_id, lang)
    if key in primary:
        return safe_format(primary[key], vars)

    # Steps 3 & 4: merged for the tenant's default lang (skip if same as lang)
    if default_lang and default_lang != lang:
        fallback = await merged_strings(session, tenant_id, default_lang)
        if key in fallback:
            return safe_format(fallback[key], vars)

    # Step 5: caller-supplied default
    if default is not None:
        return safe_format(default, vars)

    # Step 6: missing sentinel
    logger.warning("i18n_missing", key=key, lang=lang, tenant_id=tenant_id)
    return f"[missing: {key}]"
