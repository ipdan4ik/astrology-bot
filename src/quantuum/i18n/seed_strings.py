"""Canonical platform string seed data (Russian + English).

Each entry in BASE_STRINGS maps a dotted key to ``{"ru": <text>, "en": <text>}``.
The ``ru`` value is the EXACT current string used in the customer bot so that
existing behaviour is preserved when handlers switch to key-based lookups.

Keys that require runtime interpolation use ``{var}`` placeholders.
Placeholder variables per key:

    profile.name            — {name}
    profile.birth_date      — {birth_date}
    profile.birth_time      — {birth_time}
    profile.place           — {place}
    history.label           — {date}, {status}
    history.detail_header   — {id}
    history.detail_status   — {status}
    history.detail_created  — {created_at}
    history.detail_ready    — {completed_at}
    buy.plan_subscription   — {name}, {price}
    buy.plan_package        — {name}, {count}, {price}
    buy.invoice_subscription — {period_days}
    buy.invoice_package     — {count}
    profile.field_edit_error — {err}

    master.onboard.slug_prompt   — {prefill}
    master.onboard.slug_prefill  — {slug}
    master.onboard.confirm       — {slug}, {display_name}, {language}
    master.onboard.done          — {username}

    owner.tenants.line   — {display_name}, {slug}, {status}
    owner.manage.title   — {display_name}, {slug}, {status}
    owner.stats.text     — {period_days}, {active_customers}, {paid_customers},
                           {dau}, {wau}, {mau}, {revenue_cents}, {mrr_cents},
                           {requests_by_kind}
"""

BASE_STRINGS: dict[str, dict[str, str]] = {
    # -------------------------------------------------------------------------
    # Main-menu button labels
    # -------------------------------------------------------------------------
    "btn.generate": {
        "ru": "🔮 Разбор",
        "en": "🔮 Reading",
    },
    "btn.profile": {
        "ru": "👤 Профиль",
        "en": "👤 Profile",
    },
    "btn.history": {
        "ru": "📜 История",
        "en": "📜 History",
    },
    "btn.help": {
        "ru": "ℹ️ Помощь",
        "en": "ℹ️ Help",
    },
    "btn.ask": {
        "ru": "❓ Спросить астролога",
        "en": "❓ Ask the astrologer",
    },
    "btn.transits": {
        "ru": "🌌 Транзиты",
        "en": "🌌 Transits",
    },
    "btn.daily": {
        "ru": "🔔 Ежедневный гороскоп",
        "en": "🔔 Daily horoscope",
    },
    # Language selection (picker + menu button)
    "btn.language": {
        "ru": "🌐 Язык",
        "en": "🌐 Language",
    },
    # -------------------------------------------------------------------------
    # Blueprint status words (used in history labels & detail views)
    # -------------------------------------------------------------------------
    "status.pending": {
        "ru": "в очереди",
        "en": "queued",
    },
    "status.calculating": {
        "ru": "считаю",
        "en": "calculating",
    },
    "status.generating": {
        "ru": "генерирую",
        "en": "generating",
    },
    "status.done": {
        "ru": "готов",
        "en": "done",
    },
    "status.failed": {
        "ru": "ошибка",
        "en": "failed",
    },
    "status.refunded": {
        "ru": "возврат",
        "en": "refunded",
    },
    # -------------------------------------------------------------------------
    # Help text
    # -------------------------------------------------------------------------
    "help.text": {
        "ru": (
            "Я строю персональный астрологический разбор (Quantuum Blueprint) по твоим "
            "натальным данным.\n\n"
            "Меню снизу:\n"
            "🔮 Разбор — сгенерировать разбор\n"
            "👤 Профиль — посмотреть и изменить натальные данные\n"
            "📜 История — прошлые генерации\n\n"
            "Команды: /start /profile /blueprint\n"
            "Поддержка: @quantuum_support"
        ),
        "en": (
            "I build a personal astrological reading (Quantuum Blueprint) from your "
            "natal data.\n\n"
            "Bottom menu:\n"
            "🔮 Reading — generate a reading\n"
            "👤 Profile — view and edit natal data\n"
            "📜 History — past generations\n\n"
            "Commands: /start /profile /blueprint\n"
            "Support: @quantuum_support"
        ),
    },
    # -------------------------------------------------------------------------
    # Profile display (render_profile lines)
    # Placeholders: see module docstring
    # -------------------------------------------------------------------------
    "profile.title": {
        "ru": "👤 Твой профиль:",
        "en": "👤 Your profile:",
    },
    "profile.name": {
        "ru": "Имя: {name}",
        "en": "Name: {name}",
    },
    "profile.birth_date": {
        "ru": "Дата рождения: {birth_date}",
        "en": "Date of birth: {birth_date}",
    },
    "profile.birth_time": {
        "ru": "Время: {birth_time}",
        "en": "Time: {birth_time}",
    },
    "profile.place": {
        "ru": "Место: {place}",
        "en": "Place: {place}",
    },
    # -------------------------------------------------------------------------
    # Profile screen messages
    # -------------------------------------------------------------------------
    "profile.empty": {
        "ru": "Профиль не заполнен.",
        "en": "Profile not filled in.",
    },
    "profile.not_found": {
        "ru": "Профиль не найден.",
        "en": "Profile not found.",
    },
    "profile.place.confirm": {
        "ru": "Нашёл: {place}\n\nВерно?",
        "en": "Found: {place}\n\nCorrect?",
    },
    "profile.place.not_found": {
        "ru": "Не нашёл это место. Уточни город / адрес или пришли геопозицию:",
        "en": "Couldn't find that place. Refine the city / address or send a location:",
    },
    # -------------------------------------------------------------------------
    # Profile keyboard labels
    # -------------------------------------------------------------------------
    "profile.kb.fill": {
        "ru": "📝 Заполнить профиль",
        "en": "📝 Fill in profile",
    },
    "profile.kb.edit_name": {
        "ru": "✏️ Имя",
        "en": "✏️ Name",
    },
    "profile.kb.edit_birth_date": {
        "ru": "✏️ Дата",
        "en": "✏️ Date",
    },
    "profile.kb.edit_birth_time": {
        "ru": "✏️ Время",
        "en": "✏️ Time",
    },
    "profile.kb.edit_birth_place": {
        "ru": "✏️ Место",
        "en": "✏️ Place",
    },
    "profile.kb.place_confirm": {"ru": "✅ Да", "en": "✅ Yes"},
    "profile.kb.place_retry": {"ru": "✏️ Другой адрес", "en": "✏️ Different address"},
    # -------------------------------------------------------------------------
    # Profile field prompts (edit flow)
    # -------------------------------------------------------------------------
    "profile.prompt.name": {
        "ru": "Введи имя:",
        "en": "Enter your name:",
    },
    "profile.prompt.birth_date": {
        "ru": "Дата рождения ГГГГ-ММ-ДД (например 1980-06-24):",
        "en": "Date of birth YYYY-MM-DD (e.g. 1980-06-24):",
    },
    "profile.prompt.birth_time": {
        "ru": "Время рождения ЧЧ:ММ (например 10:00):",
        "en": "Time of birth HH:MM (e.g. 10:00):",
    },
    "profile.prompt.birth_place": {
        "ru": "Пришли геопозицию (📎 → Геопозиция) или напиши город / адрес:",
        "en": "Send your location (📎 → Location) or type a city / address:",
    },
    # -------------------------------------------------------------------------
    # Profile field validation errors
    # -------------------------------------------------------------------------
    "profile.error.name_empty": {
        "ru": "Имя не может быть пустым.",
        "en": "Name cannot be empty.",
    },
    "profile.error.birth_date_invalid": {
        "ru": "Не понял дату. Формат ГГГГ-ММ-ДД.",
        "en": "Could not parse date. Format YYYY-MM-DD.",
    },
    "profile.error.birth_time_invalid": {
        "ru": "Не понял время. Формат ЧЧ:ММ.",
        "en": "Could not parse time. Format HH:MM.",
    },
    "profile.error.unknown_field": {
        "ru": "Неизвестное поле.",
        "en": "Unknown field.",
    },
    # Profile edit retry message — {err} is the preceding error string
    "profile.field_edit_error": {
        "ru": "{err}\nПопробуй ещё раз:",
        "en": "{err}\nPlease try again:",
    },
    # -------------------------------------------------------------------------
    # Start / welcome
    # -------------------------------------------------------------------------
    "start.welcome": {
        "ru": "Привет! Я построю твой астрологический разбор ✨",
        "en": "Hello! I will build your astrological reading ✨",
    },
    # -------------------------------------------------------------------------
    # Main menu
    # -------------------------------------------------------------------------
    "menu.title": {
        "ru": "Главное меню:",
        "en": "Main menu:",
    },
    "menu.cancelled": {
        "ru": "Отменено.",
        "en": "Cancelled.",
    },
    # -------------------------------------------------------------------------
    # Generate (blueprint request)
    # -------------------------------------------------------------------------
    "generate.no_profile": {
        "ru": "Сначала заполни профиль:",
        "en": "Please fill in your profile first:",
    },
    "generate.no_quota": {
        "ru": "Бесплатная генерация уже использована. Купи пакет разборов или подписку:",
        "en": "Your free generation has already been used. Buy a package or subscription:",
    },
    "generate.queued": {
        "ru": "Генерирую твой разбор, это займёт около минуты…",
        "en": "Generating your reading, this will take about a minute…",
    },
    # -------------------------------------------------------------------------
    # Q&A astrologer
    # -------------------------------------------------------------------------
    "qa.ask_prompt": {
        "ru": "Напиши свой вопрос астрологу:",
        "en": "Send your question to the astrologer:",
    },
    "qa.thinking": {
        "ru": "Думаю над ответом… ⏳",
        "en": "Thinking about your answer… ⏳",
    },
    "qa.no_profile": {
        "ru": "Сначала заполни натальный профиль (/profile).",
        "en": "Fill in your natal profile first (/profile).",
    },
    "qa.no_quota": {
        "ru": "Закончились разборы. Купи пакет или подписку, чтобы спрашивать астролога:",
        "en": "You're out of credits. Buy a pack or subscription to ask the astrologer:",
    },
    "qa.too_long": {
        "ru": "Вопрос слишком длинный (макс 1000 символов).",
        "en": "Question is too long (max 1000 chars).",
    },
    "qa.empty": {
        "ru": "Вопрос пустой. Напиши вопрос:",
        "en": "Empty question. Please type your question:",
    },
    # -------------------------------------------------------------------------
    # Transits
    # -------------------------------------------------------------------------
    "transit.thinking": {
        "ru": "Считаю транзиты… ⏳",
        "en": "Calculating your transits… ⏳",
    },
    "transit.no_profile": {
        "ru": "Сначала заполни натальный профиль (/profile).",
        "en": "Fill in your natal profile first (/profile).",
    },
    "transit.no_quota": {
        "ru": "Закончились разборы. Купи пакет или подписку, чтобы посмотреть транзиты:",
        "en": "You're out of credits. Buy a pack or subscription to see your transits:",
    },
    "transit.failed": {
        "ru": "Не удалось посчитать транзиты. Попробуй позже.",
        "en": "Couldn't compute your transits. Try again later.",
    },
    # -------------------------------------------------------------------------
    # Daily horoscope
    # -------------------------------------------------------------------------
    "daily.header": {
        "ru": "🌟 Гороскоп на сегодня",
        "en": "🌟 Today's horoscope",
    },
    "daily.status_on": {
        "ru": "Ежедневный гороскоп включён. Время доставки: {hour}:00 (по твоему часовому поясу).",
        "en": "Daily horoscope is ON. Delivery time: {hour}:00 (your timezone).",
    },
    "daily.status_off": {
        "ru": "Ежедневный гороскоп выключен.",
        "en": "Daily horoscope is OFF.",
    },
    "daily.not_subscriber": {
        "ru": "Ежедневный гороскоп доступен по подписке. Оформи подписку, чтобы получать его каждое утро:",
        "en": "The daily horoscope is a subscriber feature. Subscribe to get it every morning:",
    },
    "daily.no_profile": {
        "ru": "Сначала заполни натальный профиль (/profile).",
        "en": "Fill in your natal profile first (/profile).",
    },
    "daily.enabled": {
        "ru": "Включил ежедневный гороскоп ✅",
        "en": "Daily horoscope enabled ✅",
    },
    "daily.disabled": {
        "ru": "Выключил ежедневный гороскоп.",
        "en": "Daily horoscope disabled.",
    },
    "daily.hour_set": {
        "ru": "Время доставки: {hour}:00 ✅",
        "en": "Delivery time: {hour}:00 ✅",
    },
    "daily.kb.turn_on": {
        "ru": "🔔 Включить",
        "en": "🔔 Turn on",
    },
    "daily.kb.turn_off": {
        "ru": "🔕 Выключить",
        "en": "🔕 Turn off",
    },
    # -------------------------------------------------------------------------
    # History
    # -------------------------------------------------------------------------
    "history.empty": {
        "ru": "Пока нет генераций. Нажми «🔮 Разбор», чтобы создать первую.",
        "en": "No readings yet. Tap «🔮 Reading» to create your first one.",
    },
    "history.title": {
        "ru": "📜 История генераций:",
        "en": "📜 Reading history:",
    },
    # History list item label — {date} is dd.mm, {status} is localised status word
    "history.label": {
        "ru": "🔮 {date} · {status}",
        "en": "🔮 {date} · {status}",
    },
    # Blueprint detail lines — {id}, {status}, {created_at}, {completed_at}
    "history.detail_header": {
        "ru": "🔮 Разбор #{id}",
        "en": "🔮 Reading #{id}",
    },
    "history.detail_status": {
        "ru": "Статус: {status}",
        "en": "Status: {status}",
    },
    "history.detail_created": {
        "ru": "Создан: {created_at}",
        "en": "Created: {created_at}",
    },
    "history.detail_ready": {
        "ru": "Готов: {completed_at}",
        "en": "Ready: {completed_at}",
    },
    "history.not_found": {
        "ru": "Не найдено",
        "en": "Not found",
    },
    # -------------------------------------------------------------------------
    # History / blueprint detail keyboard labels
    # -------------------------------------------------------------------------
    "history.kb.download": {
        "ru": "📥 Скачать .md",
        "en": "📥 Download .md",
    },
    "history.kb.preview": {
        "ru": "👁 Превью",
        "en": "👁 Preview",
    },
    "history.kb.back": {
        "ru": "← Назад",
        "en": "← Back",
    },
    "history.kb.prev_page": {
        "ru": "← Пред",
        "en": "← Prev",
    },
    "history.kb.next_page": {
        "ru": "След →",
        "en": "Next →",
    },
    "history.unavailable": {
        "ru": "Недоступно",
        "en": "Unavailable",
    },
    # -------------------------------------------------------------------------
    # Buy / payments
    # -------------------------------------------------------------------------
    "buy.menu_title": {
        "ru": "Выбери, что купить (оплата звёздами Telegram ★):",
        "en": "Choose what to buy (payment via Telegram Stars ★):",
    },
    "buy.no_plans": {
        "ru": "Пока нет доступных планов. Загляни позже.",
        "en": "No plans available yet. Check back later.",
    },
    # Plan button labels — {name}/{price} for subscription, +{count} for package
    "buy.plan_subscription": {
        "ru": "⭐ {name} — {price}★",
        "en": "⭐ {name} — {price}★",
    },
    "buy.plan_package": {
        "ru": "⭐ {name} · {count} разборов — {price}★",
        "en": "⭐ {name} · {count} readings — {price}★",
    },
    # Invoice description strings — {period_days} / {count}
    "buy.invoice_subscription": {
        "ru": "Подписка на {period_days} дней",
        "en": "Subscription for {period_days} days",
    },
    "buy.invoice_package": {
        "ru": "Пакет: {count} разборов",
        "en": "Package: {count} readings",
    },
    "buy.plan_unavailable": {
        "ru": "Этот план больше недоступен.",
        "en": "This plan is no longer available.",
    },
    "buy.payment_success": {
        "ru": "Оплата получена! Доступ активирован. ✨",
        "en": "Payment received! Access activated. ✨",
    },
    "buy.payment_already_credited": {
        "ru": "Эта оплата уже была учтена ранее.",
        "en": "This payment has already been credited.",
    },
    # Buy offer inline button (shown when quota exhausted)
    "buy.kb.open": {
        "ru": "💳 Купить разборы",
        "en": "💳 Buy readings",
    },
    # -------------------------------------------------------------------------
    # Shared / generic
    # -------------------------------------------------------------------------
    "kb.cancel": {
        "ru": "✖️ Отмена",
        "en": "✖️ Cancel",
    },
    # -------------------------------------------------------------------------
    # Master bot — owner onboarding (master_onboarding.py)
    # -------------------------------------------------------------------------
    "master.onboard.invite_invalid": {
        "ru": "Приглашение недействительно или истекло.",
        "en": "The invitation is invalid or has expired.",
    },
    # Slug prompt — {prefill} is the optional suggested-slug suffix (may be empty)
    "master.onboard.slug_prompt": {
        "ru": "Добро пожаловать! Давай создадим бота. Введи slug тенанта (латиница, без пробелов){prefill}:",
        "en": "Welcome! Let's create a bot. Enter the tenant slug (latin letters, no spaces){prefill}:",
    },
    # Suggested-slug suffix appended to the slug prompt — {slug} is the preset slug
    "master.onboard.slug_prefill": {
        "ru": " (предложено: {slug})",
        "en": " (suggested: {slug})",
    },
    "master.onboard.plain_start": {
        "ru": "Это бот онбординга платформы. Открой ссылку-приглашение, чтобы создать своего бота.",
        "en": "This is the platform onboarding bot. Open an invitation link to create your own bot.",
    },
    "master.onboard.slug_invalid": {
        "ru": "Slug не должен быть пустым или содержать пробелы. Попробуй ещё раз:",
        "en": "The slug must not be empty or contain spaces. Please try again:",
    },
    "master.onboard.slug_taken": {
        "ru": "Этот slug уже занят. Введи другой:",
        "en": "This slug is already taken. Enter another one:",
    },
    "master.onboard.display_name_prompt": {
        "ru": "Отображаемое имя продукта (например «Acme Astro»):",
        "en": "Product display name (e.g. «Acme Astro»):",
    },
    "master.onboard.display_name_empty": {
        "ru": "Имя не должно быть пустым. Введи ещё раз:",
        "en": "The name must not be empty. Enter it again:",
    },
    "master.onboard.lang_prompt": {
        "ru": "Язык по умолчанию (двухбуквенный код, например ru или en):",
        "en": "Default language (two-letter code, e.g. ru or en):",
    },
    "master.onboard.lang_invalid": {
        "ru": "Нужен двухбуквенный код языка, например ru. Введи ещё раз:",
        "en": "A two-letter language code is required, e.g. ru. Enter it again:",
    },
    # Confirmation summary — {slug}, {display_name}, {language}
    # NB: the placeholder is {language}, NOT {lang}: the Translator reserves `lang`
    # (the resolution language), so a `lang=` format var collides in t().
    "master.onboard.confirm": {
        "ru": (
            "Проверь данные:\nslug: {slug}\nназвание: {display_name}\nязык: {language}\n\n"
            "Создаём бота?"
        ),
        "en": (
            "Check the details:\nslug: {slug}\nname: {display_name}\nlanguage: {language}\n\n"
            "Create the bot?"
        ),
    },
    "master.onboard.invite_gone": {
        "ru": "Приглашение больше недействительно.",
        "en": "The invitation is no longer valid.",
    },
    "master.onboard.creating": {
        "ru": "Создаю тенанта… Проверяю возможность автосоздания бота.",
        "en": "Creating the tenant… Checking whether the bot can be created automatically.",
    },
    "master.onboard.cancelled": {
        "ru": "Онбординг отменён.",
        "en": "Onboarding cancelled.",
    },
    "master.onboard.token_invalid": {
        "ru": "Это не похоже на валидный токен бота. Пришли токен от @BotFather ещё раз:",
        "en": "This doesn't look like a valid bot token. Send the token from @BotFather again:",
    },
    # Done message — {username} is the activated bot username (without @)
    "master.onboard.done": {
        "ru": "Готово! Бот @{username} активирован. Он станет доступен после перезапуска воркера.",
        "en": "Done! Bot @{username} is activated. It will become available after the worker restarts.",
    },
    # Master onboarding keyboard labels
    "master.kb.cancel": {
        "ru": "Отмена",
        "en": "Cancel",
    },
    "master.kb.create_bot": {
        "ru": "Создать бота",
        "en": "Create bot",
    },
    # -------------------------------------------------------------------------
    # Master bot — owner console (owner_console.py)
    # -------------------------------------------------------------------------
    # /tenants
    "owner.tenants.empty": {
        "ru": "У тебя пока нет тенантов. Создай бота по ссылке-приглашению.",
        "en": "You don't have any tenants yet. Create a bot via an invitation link.",
    },
    "owner.tenants.header": {
        "ru": "Твои тенанты:",
        "en": "Your tenants:",
    },
    # Per-tenant list line — {display_name}, {slug}, {status}
    "owner.tenants.line": {
        "ru": "• {display_name} (/{slug}) — {status}",
        "en": "• {display_name} (/{slug}) — {status}",
    },
    "owner.tenants.hint": {
        "ru": "\nУправление: /manage <slug>",
        "en": "\nManage: /manage <slug>",
    },
    # /manage
    "owner.manage.usage": {
        "ru": "Использование: /manage <slug>",
        "en": "Usage: /manage <slug>",
    },
    "owner.manage.not_found": {
        "ru": "Тенант не найден или у тебя нет прав.",
        "en": "Tenant not found or you don't have permission.",
    },
    # Manage screen title — {display_name}, {slug}, {status}
    "owner.manage.title": {
        "ru": "Управление: {display_name} (/{slug}) — {status}",
        "en": "Manage: {display_name} (/{slug}) — {status}",
    },
    # /manage keyboard labels
    "owner.manage.kb.stats": {
        "ru": "📊 Статистика",
        "en": "📊 Statistics",
    },
    "owner.manage.kb.pause": {
        "ru": "⏸ Пауза",
        "en": "⏸ Pause",
    },
    "owner.manage.kb.resume": {
        "ru": "▶️ Возобновить",
        "en": "▶️ Resume",
    },
    "owner.manage.kb.transfer": {
        "ru": "🔁 Передать владение",
        "en": "🔁 Transfer ownership",
    },
    # Stats text — see module docstring for placeholders
    "owner.stats.text": {
        "ru": (
            "📊 Статистика (за {period_days} дн.)\n"
            "Активные: {active_customers}, платящие: {paid_customers}\n"
            "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
            "Выручка: {revenue_cents}, MRR: {mrr_cents}\n"
            "Запросы: {requests_by_kind}"
        ),
        "en": (
            "📊 Statistics (last {period_days} days)\n"
            "Active: {active_customers}, paying: {paid_customers}\n"
            "DAU/WAU/MAU: {dau}/{wau}/{mau}\n"
            "Revenue: {revenue_cents}, MRR: {mrr_cents}\n"
            "Requests: {requests_by_kind}"
        ),
    },
    # Authorization alert (shown via query.answer(show_alert=True))
    "owner.no_rights": {
        "ru": "Нет прав",
        "en": "No permission",
    },
    # pause / resume
    "owner.pause.platform_blocked": {
        "ru": "Нельзя поставить на паузу платформенный тенант",
        "en": "The platform tenant cannot be paused",
    },
    "owner.pause.done": {
        "ru": "⏸ Поставлено на паузу.",
        "en": "⏸ Paused.",
    },
    "owner.resume.done": {
        "ru": "▶️ Возобновлено.",
        "en": "▶️ Resumed.",
    },
    # Owner console — delete (SP2)
    "owner.manage.kb.delete": {
        "ru": "🗑 Удалить",
        "en": "🗑 Delete",
    },
    "owner.delete.prompt": {
        "ru": (
            "⚠️ Это навсегда удалит бота и скроет тенант. "
            "Чтобы подтвердить, отправь слаг: {slug}\n(или /cancel)"
        ),
        "en": (
            "⚠️ This permanently deletes the bot and hides the tenant. "
            "To confirm, send the slug: {slug}\n(or /cancel)"
        ),
    },
    "owner.delete.mismatch": {
        "ru": "Слаг не совпадает. Отправь {slug} ещё раз или /cancel.",
        "en": "Slug doesn't match. Send {slug} again or /cancel.",
    },
    "owner.delete.done": {
        "ru": "🗑 Бот удалён.",
        "en": "🗑 Bot deleted.",
    },
    "owner.delete.cancelled": {
        "ru": "Отменено.",
        "en": "Cancelled.",
    },
    "owner.delete.platform_blocked": {
        "ru": "Нельзя удалить платформенный тенант",
        "en": "The platform tenant cannot be deleted",
    },
    # Superadmin cabinet (SP1, master bot /admin)
    "admin.denied": {
        "ru": "Недостаточно прав.",
        "en": "Not authorized.",
    },
    "admin.menu.title": {
        "ru": "🛠 Панель суперадмина",
        "en": "🛠 Superadmin panel",
    },
    "admin.menu.kb.tenants": {
        "ru": "🏢 Боты",
        "en": "🏢 Bots",
    },
    "admin.menu.kb.invites": {
        "ru": "🎟 Инвайты",
        "en": "🎟 Invites",
    },
    "admin.tenants.title": {
        "ru": "Все боты:",
        "en": "All bots:",
    },
    "admin.tenants.empty": {
        "ru": "Ботов пока нет.",
        "en": "No bots yet.",
    },
    "admin.tenant.title": {
        "ru": "Бот: {display_name} (/{slug}) — {status}",
        "en": "Bot: {display_name} (/{slug}) — {status}",
    },
    "admin.tenant.kb.stats": {
        "ru": "📊 Статистика",
        "en": "📊 Stats",
    },
    "admin.tenant.kb.suspend": {
        "ru": "⏸ Приостановить",
        "en": "⏸ Suspend",
    },
    "admin.tenant.kb.resume": {
        "ru": "▶️ Возобновить",
        "en": "▶️ Resume",
    },
    "admin.tenant.kb.delete": {
        "ru": "🗑 Удалить",
        "en": "🗑 Delete",
    },
    "admin.kb.back": {
        "ru": "⬅️ Назад",
        "en": "⬅️ Back",
    },
    "admin.tenant.suspended": {
        "ru": "⏸ Бот приостановлен.",
        "en": "⏸ Bot suspended.",
    },
    "admin.tenant.resumed": {
        "ru": "▶️ Бот возобновлён.",
        "en": "▶️ Bot resumed.",
    },
    "admin.invites.title": {
        "ru": "Активные инвайты:",
        "en": "Active invites:",
    },
    "admin.invites.empty": {
        "ru": "Активных инвайтов нет.",
        "en": "No active invites.",
    },
    "admin.invites.kb.new": {
        "ru": "➕ Новый инвайт",
        "en": "➕ New invite",
    },
    "admin.invite.kb.revoke": {
        "ru": "🗑 Отозвать",
        "en": "🗑 Revoke",
    },
    "admin.invite.created": {
        "ru": "Инвайт создан:\n{link}",
        "en": "Invite created:\n{link}",
    },
    "admin.invite.revoked": {
        "ru": "Инвайт отозван.",
        "en": "Invite revoked.",
    },
    "admin.stale": {
        "ru": "Не найдено — список обновлён.",
        "en": "Not found — list refreshed.",
    },
    # /transfer
    "owner.transfer.usage": {
        "ru": "Использование: /transfer <slug>",
        "en": "Usage: /transfer <slug>",
    },
    "owner.transfer.not_owner": {
        "ru": "Тенант не найден или ты не владелец.",
        "en": "Tenant not found or you are not the owner.",
    },
    "owner.transfer.prompt": {
        "ru": (
            "Перешли Telegram ID нового владельца (число). "
            "Он должен уже иметь аккаунт в этом тенанте (запустить твоего бота)."
        ),
        "en": (
            "Forward the Telegram ID of the new owner (a number). "
            "They must already have an account in this tenant (have started your bot)."
        ),
    },
    "owner.transfer.cancelled": {
        "ru": "Отменено.",
        "en": "Cancelled.",
    },
    "owner.transfer.target_invalid": {
        "ru": "Нужен числовой Telegram ID. Попробуй ещё раз или /cancel.",
        "en": "A numeric Telegram ID is required. Try again or /cancel.",
    },
    "owner.transfer.no_rights_anymore": {
        "ru": "Больше нет прав на передачу.",
        "en": "You no longer have permission to transfer.",
    },
    "owner.transfer.no_account": {
        "ru": (
            "У этого пользователя нет аккаунта в тенанте. "
            "Он должен сначала запустить твоего бота."
        ),
        "en": (
            "This user has no account in the tenant. "
            "They must start your bot first."
        ),
    },
    "owner.transfer.done": {
        "ru": "✅ Готово. Владение передано.",
        "en": "✅ Done. Ownership transferred.",
    },
    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    "lang.prompt": {
        "ru": "Выбери язык:",
        "en": "Choose your language:",
    },
    "lang.changed": {
        "ru": "Язык изменён.",
        "en": "Language updated.",
    },
    # -------------------------------------------------------------------------
    # Onboarding flow (onboarding.py) — RU values are the exact pre-i18n literals
    # -------------------------------------------------------------------------
    "onb.prompt.full_name": {
        "ru": "Введи полное имя (как в свидетельстве о рождении):",
        "en": "Enter your full name (as on your birth certificate):",
    },
    "onb.error.full_name": {
        "ru": "Не понял имя. Введи полное имя текстом:",
        "en": "Couldn't read the name. Enter your full name as text:",
    },
    "onb.prompt.birth_date": {
        "ru": "Дата рождения в формате ГГГГ-ММ-ДД (например 1980-06-24):",
        "en": "Date of birth in YYYY-MM-DD format (e.g. 1980-06-24):",
    },
    "onb.error.birth_date": {
        "ru": "Не понял дату. Формат ГГГГ-ММ-ДД:",
        "en": "Couldn't read the date. Format YYYY-MM-DD:",
    },
    "onb.prompt.birth_time": {
        "ru": "Время рождения ЧЧ:ММ (например 10:00):",
        "en": "Time of birth HH:MM (e.g. 10:00):",
    },
    "onb.error.birth_time": {
        "ru": "Не понял время. Формат ЧЧ:ММ:",
        "en": "Couldn't read the time. Format HH:MM:",
    },
    "onb.prompt.birth_place": {
        "ru": (
            "Место рождения: пришли геопозицию (📎 → Геопозиция, можно поставить точку "
            "на карте) или напиши город / часть адреса:"
        ),
        "en": (
            "Place of birth: send your location (📎 → Location, you can drop a pin on the "
            "map) or type a city / part of an address:"
        ),
    },
    "onb.done": {
        "ru": "Готово! Профиль сохранён. Команда /blueprint сгенерирует твой разбор.",
        "en": "Done! Your profile is saved. The /blueprint command will generate your reading.",
    },
    # -------------------------------------------------------------------------
    # Owner console — user management (list / credits / ban)
    # -------------------------------------------------------------------------
    "owner.manage.kb.users": {"ru": "👥 Пользователи", "en": "👥 Users"},
    "owner.users.header": {
        "ru": "Пользователи бота {display_name}:",
        "en": "Users of {display_name}:",
    },
    "owner.users.empty": {"ru": "Пока нет пользователей.", "en": "No users yet."},
    "owner.users.row": {"ru": "{name} · {credits}💎", "en": "{name} · {credits}💎"},
    "owner.users.unnamed": {"ru": "пользователь #{id}", "en": "user #{id}"},
    "owner.users.nav.prev": {"ru": "◀️", "en": "◀️"},
    "owner.users.nav.next": {"ru": "▶️", "en": "▶️"},
    "owner.user.card": {
        "ru": (
            "👤 {name}\nTelegram ID: {tg_id}\nКредиты: {credits}💎\n"
            "Подписка: {subscription}\nСтатус: {status}"
        ),
        "en": (
            "👤 {name}\nTelegram ID: {tg_id}\nCredits: {credits}💎\n"
            "Subscription: {subscription}\nStatus: {status}"
        ),
    },
    "owner.user.card.banned": {
        "ru": "🚫 Забанен. Причина: {reason}",
        "en": "🚫 Banned. Reason: {reason}",
    },
    "owner.user.status.active": {"ru": "активен", "en": "active"},
    "owner.user.status.banned": {"ru": "забанен", "en": "banned"},
    "owner.user.not_found": {"ru": "Пользователь не найден.", "en": "User not found."},
    "owner.user.kb.grant": {"ru": "💎 Изменить кредиты", "en": "💎 Adjust credits"},
    "owner.user.kb.ban": {"ru": "🚫 Забанить", "en": "🚫 Ban"},
    "owner.user.kb.unban": {"ru": "✅ Разбанить", "en": "✅ Unban"},
    "owner.user.kb.back": {"ru": "⬅️ К списку", "en": "⬅️ To list"},
    "owner.user.grant.prompt": {
        "ru": "Введите число кредитов (можно отрицательное, напр. -3):",
        "en": "Enter the number of credits (can be negative, e.g. -3):",
    },
    "owner.user.grant.invalid": {
        "ru": "Не понял. Введите целое число, напр. 5 или -2.",
        "en": "I didn't get that. Enter a whole number, e.g. 5 or -2.",
    },
    "owner.user.grant.done": {
        "ru": "Готово. Новый баланс: {credits}💎.",
        "en": "Done. New balance: {credits}💎.",
    },
    "owner.user.ban.prompt": {"ru": "Укажите причину бана:", "en": "Enter the ban reason:"},
    "owner.user.ban.invalid": {
        "ru": "Причина не может быть пустой. Укажите причину:",
        "en": "The reason can't be empty. Enter a reason:",
    },
    "owner.user.ban.done": {"ru": "Пользователь забанен.", "en": "User banned."},
    "owner.user.ban.staff_blocked": {
        "ru": "Нельзя забанить владельца или администратора.",
        "en": "You can't ban an owner or admin.",
    },
    "owner.user.unban.done": {"ru": "Пользователь разбанен.", "en": "User unbanned."},
    "owner.user.cancelled": {"ru": "Отменено.", "en": "Cancelled."},
    "account.banned.notice": {
        "ru": "🚫 Доступ к боту ограничен. Причина: {reason}",
        "en": "🚫 Your access to the bot is restricted. Reason: {reason}",
    },
}

# Merge the per-language translation files into BASE_STRINGS. Only keys that
# already exist in the ru/en base are populated; coverage is enforced by tests.
from quantuum.i18n.translations import LANGUAGES as _EXTRA_LANGUAGES  # noqa: E402

for _lang, _mapping in _EXTRA_LANGUAGES.items():
    for _key, _text in _mapping.items():
        if _key in BASE_STRINGS:
            BASE_STRINGS[_key][_lang] = _text
