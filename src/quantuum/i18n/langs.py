"""Single source of truth for the platform's supported languages."""

DEFAULT_LANG = "ru"

# Display/seed order. ru first (default), en second, then the rest.
PLATFORM_LANGS: tuple[str, ...] = (
    "ru", "en", "es", "fr", "pt", "it", "de", "tr", "zh", "hi",
)

# Non-default languages, used as the default extra_langs for tenant seeding.
EXTRA_LANGS: tuple[str, ...] = tuple(c for c in PLATFORM_LANGS if c != DEFAULT_LANG)
