from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.db.session import get_sessionmaker
from quantuum.i18n.cache import get_cached_strings
from quantuum.i18n.strings import get_enabled_langs, get_tenant_default_lang
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

FALLBACK_LANG = "en"


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
    primary = await get_cached_strings(session, tenant_id, lang)
    if key in primary:
        return safe_format(primary[key], vars)

    # Steps 3 & 4: merged for the tenant's default lang (skip if same as lang)
    if default_lang and default_lang != lang:
        fallback = await get_cached_strings(session, tenant_id, default_lang)
        if key in fallback:
            return safe_format(fallback[key], vars)

    # Step 5: caller-supplied default
    if default is not None:
        return safe_format(default, vars)

    # Step 6: missing sentinel
    logger.warning("i18n_missing", key=key, lang=lang, tenant_id=tenant_id)
    return f"[missing: {key}]"


async def resolve_lang(
    session: AsyncSession,
    *,
    tenant_id: int,
    preferred_lang: str | None,
    tg_language_code: str | None,
) -> str:
    """Return the best available language for this user.

    Candidates are tried in order: ``preferred_lang``, then ``tg_language_code``.
    For each candidate we perform an exact string match against the set of enabled
    languages for the tenant (no locale normalisation — MVP only).  If neither
    candidate matches we fall back to the tenant default lang, and finally to
    ``FALLBACK_LANG`` ("en") if no default is configured.
    """
    enabled = await get_enabled_langs(session, tenant_id)
    for candidate in (preferred_lang, tg_language_code):
        if candidate and candidate in enabled:
            return candidate
    default = await get_tenant_default_lang(session, tenant_id)
    return default or FALLBACK_LANG


class Translator:
    """Thin facade that binds a resolved language to a tenant for handler use.

    ``__call__`` opens its own short-lived DB session for each translation lookup.
    Because ``t()`` is backed by the Redis cache this rarely hits the database
    after the cache is warm, so the session overhead is negligible.
    """

    def __init__(self, *, tenant_id: int, lang: str) -> None:
        self.tenant_id = tenant_id
        self.lang = lang

    async def __call__(
        self, key: str, default: str | None = None, **vars
    ) -> str:
        async with get_sessionmaker()() as session:
            return await t(
                session,
                key,
                self.lang,
                tenant_id=self.tenant_id,
                default=default,
                **vars,
            )

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        preferred_lang: str | None,
        tg_language_code: str | None,
    ) -> "Translator":
        """Resolve the user's language and return a ready-to-use Translator."""
        lang = await resolve_lang(
            session,
            tenant_id=tenant_id,
            preferred_lang=preferred_lang,
            tg_language_code=tg_language_code,
        )
        return cls(tenant_id=tenant_id, lang=lang)
