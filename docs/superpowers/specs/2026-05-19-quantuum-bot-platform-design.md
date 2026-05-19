# Quantuum Bot Platform — Design

**Status:** Draft (post-brainstorm), awaiting plan
**Date:** 2026-05-19
**Owner:** TBD

## 1. Overview

Multi-tenant SaaS-платформа для астрологических Telegram-ботов. Ядро продукта — генерация персонального астрологического отчёта (Quantuum Blueprint) на основе натальных данных пользователя: детерминированный расчёт (Western/Vedic астрология, нумерология, Chinese BaZi, Human Design, Gene Keys, Mayan Tzolkin) + LLM-полировка в премиальный нарратив. Платформа поддерживает множественные тенанты (несколько ботов под разных овнеров-франчайзи) с общим кодом и БД.

В MVP запускается один тенант (платформенный собственный продукт) на одном Telegram-боте, но архитектура мультитенантная с первого коммита.

### Goals
- Запуск рабочего бота с генерацией Blueprint (моки на старте, реальная астрология после порта движка).
- Полная мультитенантная архитектура (row-level tenancy), готовая к добавлению франчайзи-тенантов.
- Платёжная подсистема через Telegram Stars (абстракция готова к CloudPayments / CryptoBot).
- Публичный REST API + админ-API (без фронта в MVP).
- Auth: Telegram OAuth (новый), email magic link, telegram chat-identity внутри ботов.
- Онбординг новых тенантов — через мастер-бот по invite-коду от суперадмина.

### Non-goals (MVP)
- Веб-сайт / лендинг / личный кабинет.
- CloudPayments, CryptoBot интеграции.
- Q&A с астрологом-LLM, transit-апдейты, personal year, compatibility.
- Авто-выплаты Basic-тенантам.
- Активация VIP-тира с платежом лицензии end-to-end (только модель данных).
- Поддержка MAX и VK ботов (только архитектурная подготовка).
- Авто-перевод i18n.
- Web admin UI.

## 2. Tech stack

- **Язык:** Python 3.12+
- **Веб:** FastAPI
- **Telegram:** aiogram 3.x
- **БД:** PostgreSQL 16, SQLModel (поверх SQLAlchemy 2.x + Pydantic v2)
- **Миграции:** Alembic
- **Очередь / кеш:** Redis 7
- **Воркеры:** arq
- **LLM:** прямой SDK провайдера (по умолчанию `anthropic`), абстракция через `LLMClient` Protocol; альтернативы — `openai`, `mistralai`
- **Logging:** `structlog` + JSON формат
- **Тесты:** pytest, pytest-asyncio, фикстуры под движок астрологии
- **Container:** Docker, docker-compose
- **Деплой:** один VPS, `docker-compose up`

## 3. Architecture / process topology

Три процесса в одном docker-compose, общая БД и Redis:

### `api` — FastAPI, port 8000
- Публичный REST (`/v1/...`)
- Auth (`/auth/...`)
- Admin API (`/admin/tenants/...`, `/admin/platform/...`)
- Webhook-приёмник Telegram: `POST /tg/{webhook_secret_path}` — валидирует тенанта по `webhook_secret_path`, пушит update в Redis-очередь, отвечает 200 OK быстро.
- Платёжные callback-ендпоинты: `POST /payments/callback/{provider_kind}`.

### `bot-worker` — aiogram 3
Источников апдейтов два:
- Redis-очередь (для webhook-тенантов).
- `Dispatcher.start_polling(*bots)` (для polling-тенантов; на старте процесса достаёт всех тенантов с `transport=polling` и запускает один общий polling-loop).

Общий `Router` с хендлерами. `bot` инжектится в каждый хендлер. Middleware:
- Tenant resolution (по `bot.id` → `tenant_id`).
- Account resolution (по `from_user.id` + tenant_id → `account_id`).
- Rate-limit per-tenant (Redis-counter, токен-бакет).
- Language resolution.

Если хендлеру нужна LLM или долгая операция — кладёт arq-таск, отвечает «генерирую…».

### `task-worker` — arq
Тяжёлые таски:
- `blueprint_generate(blueprint_id)` — детерминированный расчёт + LLM-полировка + отправка результата пользователю.
- `provision_tenant(tenant_id)` — программное создание Telegram-бота / фолбэк-ожидание токена / set_webhook / seed конфига.
- В будущем: `qa_generate`, `transit_generate`, `i18n_autotranslate`.

Retry, exponential backoff, dead-letter queue. После выполнения шлёт результат пользователю через тот же бот.

### Infrastructure
- **Postgres**: одна БД, одна схема, row-level tenancy через колонку `tenant_id`. Postgres RLS планируется как «второй замок» (миграция позже, без переписки кода — middleware будет ставить `SET LOCAL app.tenant_id`).
- **Redis**: update queue, arq broker, rate-limit counters, кеш конфигов и i18n.

### Транспорт per-tenant
- `tenant_bots.transport ∈ {webhook, polling}`.
- При смене `transport` — операция администратора: webhook → polling: `bot.delete_webhook()`, добавление в polling-pool. polling → webhook: добавление webhook URL, удаление из polling-pool.

## 4. Data model

Все доменные таблицы имеют `tenant_id`. Superadmin использует `tenant_id IS NULL`.

### Tenancy
```
tenants
  id, slug (unique), display_name,
  tier (basic|vip), status (provisioning|awaiting_manual_token|active|paused|suspended|archived),
  is_platform (bool, default false),
  primary_owner_account_id (FK accounts, NULL до provisioning),
  owner_tg_id (text, NULL — Telegram ID owner-а; ставится в момент использования invite, нужен для provision),
  owner_chat_id (text, NULL — chat_id для нотификаций мастер-ботом owner-а),
  created_at, updated_at

tenant_bots
  id, tenant_id (FK), bot_telegram_id (NULL до get_me), bot_username,
  bot_token_enc (bytea, AES-GCM),
  transport (webhook|polling), webhook_secret_path (random URL-safe),
  status (provisioning|active|paused|error),
  created_at, updated_at
  -- в MVP 1:1 с tenants, в будущем тенант может иметь несколько ботов
```

### Identity & access
```
accounts
  id, tenant_id (NULL для superadmin),
  is_superadmin (bool, default false),
  preferred_lang (varchar, NULL),
  status (active|disabled),
  last_seen_at, created_at

account_identities
  id, account_id (FK),
  provider (tg_chat|tg_oauth|magic_link),
  provider_user_id (text, NULL для magic_link),
  email (text, NULL для tg_*),
  verified_at, created_at
  unique(provider, provider_user_id) where provider_user_id IS NOT NULL
  unique(provider, email) where email IS NOT NULL

account_refresh_tokens
  id, account_id, token_hash, expires_at, revoked_at, created_at

tenant_roles
  id, tenant_id (FK), account_id (FK),
  role (text, slug — owner|admin|...),
  granted_by_account_id, granted_at
  unique(tenant_id, account_id, role)
  -- инвариант "account.tenant_id = tenant_roles.tenant_id" поддерживается
  -- в коде доменного сервиса (CHECK не может ссылаться на другую таблицу);
  -- опционально включается trigger-валидацией в Postgres
```

### Astrology domain
```
natal_profiles
  id, tenant_id, account_id (FK, unique within tenant — 1:1 в MVP),
  full_name, birth_date (date), birth_time (time),
  birth_place (text), latitude (numeric), longitude (numeric),
  timezone (text — IANA или ±HH:MM),
  for_year (int, NULL),
  created_at, updated_at

blueprints
  id, tenant_id, account_id, natal_profile_id (FK),
  status (pending|calculating|generating|done|failed),
  calc_md (text), llm_md (text),
  llm_provider, llm_model, llm_tokens_in, llm_tokens_out,
  error (text, NULL),
  created_at, completed_at

requests
  id, tenant_id, account_id,
  kind (blueprint|qa|transit|...),
  reference_id (FK к blueprint/qa/... по kind), reference_type,
  status (pending|done|failed|refunded),
  cost_units (int, default 1),
  charged_against (trial|subscription|package|none),
  created_at, completed_at
```

### Billing
```
subscription_plans
  id, tenant_id (NULL = глобальный),
  slug, name (jsonb {lang: text} либо string-key к i18n),
  period (text — '1 month'|'1 year'|...), price_cents, currency,
  active, created_at

package_plans
  id, tenant_id (NULL = глобальный),
  slug, name, request_count, price_cents, currency,
  expires_after (interval, NULL = бессрочно),
  active, created_at

account_subscriptions
  id, tenant_id, account_id, plan_id,
  status (active|grace|expired|cancelled),
  started_at, ends_at, renewed_at, cancelled_at,
  payment_provider_id, external_subscription_id,
  created_at

account_packages
  id, tenant_id, account_id, plan_id,
  requests_remaining (int), purchased_at, expires_at (NULL = бессрочно),
  payment_id (FK), created_at

account_balance
  account_id (PK),
  free_trial_used (bool, default false),
  subscription_active_until (timestamp NULL),
  package_credits (int, default 0),
  updated_at

payment_providers
  id, tenant_id, kind (tg_stars|cloudpayments|cryptobot),
  config_enc (bytea), active, created_at

payments
  id, tenant_id, account_id, provider_id,
  amount_cents, currency, external_id, status (pending|paid|refunded|failed),
  metadata_jsonb,
  created_at, paid_at, refunded_at

payouts                                  -- Basic-тенантам
  id, tenant_id, period_start, period_end,
  gross_amount_cents, platform_fee_cents, net_amount_cents, currency,
  status (calculated|paid), paid_at, external_ref, calculated_by_account_id,
  created_at

tenant_licenses                          -- VIP, в MVP только таблица
  id, tenant_id, status, started_at, ends_at, price_cents, currency,
  payment_provider_id, created_at
```

### Config & i18n
```
platform_config
  key (PK), value_jsonb, updated_at, updated_by_account_id

tenant_config
  tenant_id, key, value_jsonb, updated_at, updated_by_account_id
  PK (tenant_id, key)

platform_strings
  key, lang, text
  PK (key, lang)

tenant_string_overrides
  tenant_id, key, lang, text, updated_at, updated_by_account_id
  PK (tenant_id, key, lang)

tenant_languages
  tenant_id, lang, enabled (bool), is_default (bool), created_at
  PK (tenant_id, lang)
  -- ровно одна строка на тенант с is_default=true
```

### Onboarding
```
tenant_invites
  id, code (unique random URL-safe),
  created_by_account_id (superadmin),
  tier (basic|vip), max_uses (default 1), used_count (default 0),
  expires_at, status (active|used|expired|revoked),
  preset_slug, preset_display_name, preset_username, preset_default_lang,  -- опциональные
  created_at, used_at
```

### Audit
```
audit_log
  id, tenant_id (NULL для платформенных действий),
  actor_account_id,
  action (text), entity_type, entity_id,
  payload_jsonb (before/after snapshot),
  request_id, ip_address, user_agent,
  created_at
```

### Indexes
- На всех event-таблицах (`requests`, `payments`, `blueprints`): `(tenant_id, created_at DESC)`.
- На lookup-таблицах: `(tenant_id, status)` где запросы фильтруют по статусу.
- На `account_identities`: `(provider, provider_user_id)` и `(provider, email)` — unique.
- На `tenant_bots`: unique `(bot_telegram_id)` (один бот в одном тенанте).
- На `tenants`: unique `(slug)`.
- На `account_subscriptions`: partial unique `(account_id, plan_id) WHERE status IN ('active','grace')` (см. callback handling).
- На `tenant_languages`: partial unique `(tenant_id) WHERE is_default = true` (ровно один дефолтный язык на тенант).

### Tenant resolution rules
- Кастомер: `accounts.tenant_id = X` + нет `tenant_roles` записи.
- Owner/admin: `accounts.tenant_id = X` + есть `tenant_roles(tenant_id=X, role=...)`.
- Superadmin: `accounts.tenant_id IS NULL` + `is_superadmin=true`.
- Один Telegram-юзер, использующий несколько ботов, имеет отдельный `account` в каждом тенанте, но идентифицируется одним `account_identities.provider_user_id` (поиск кросс-тенантный по identity, но домен изолирован).
- Owner, использующий свой же продуктовый бот, имеет два аккаунта: один в `platform-tenant` (для self-service в мастер-боте), один в собственном тенанте (для покупок в своём боте).

## 5. Identity & auth

### Принципалы и провайдеры

| Принципал | Логинится через | Провайдеры |
|---|---|---|
| Customer внутри бота | aiogram middleware | `tg_chat` (по `from_user.id`) |
| Customer на публичном API | `/auth/...` | `tg_oauth` (новый Telegram OAuth) или `magic_link` |
| Tenant owner/admin | мастер-бот / admin API | `tg_chat` (мастер-бот) или `magic_link` |
| Superadmin | admin API | `magic_link` или `tg_oauth` (whitelist email + tg_id) |

### Magic link flow (email)
1. `POST /auth/magic/request { email, tenant_slug? }` — бэк генерит одноразовый токен (UUID + entropy), кладёт в Redis (TTL 15 минут) с привязкой `(email, tenant_id)`. Шлёт письмо с `https://api/auth/magic/consume?token=...`.
2. `GET /auth/magic/consume?token=...` — валидируем, ищем/создаём `account` + `account_identities(provider=magic_link)`. Для superadmin: проверка `email` в `platform_config.superadmin_emails`. Возвращаем JWT + refresh.

### Telegram OAuth flow (новый)
1. `GET /auth/tg/start?tenant_slug=...` → 302 на `https://oauth.telegram.org/auth?bot_id=<master_bot_id>&...&state=<signed_state>`.
2. `GET /auth/tg/callback?...` → валидация подписи Telegram, чтение `tg_user_id`, ищем/создаём `account` + `account_identities(provider=tg_oauth)`. Для superadmin: проверка `tg_user_id` в `platform_config.superadmin_telegram_ids`. JWT + refresh.

### Customer в Telegram-боте
- Aiogram middleware: `from_user.id` + tenant → `accounts` (создаём при первом сообщении).
- Не требует OAuth — Telegram chat сам по себе доверенный канал.

### Linking
- Customer в боте может добавить email: `[Привязать email]` → magic_link → подтверждение → новая запись в `account_identities(provider=magic_link)` для того же `account_id`.
- Customer на API может добавить Telegram: `[Привязать Telegram]` → tg_oauth flow → запись `account_identities(provider=tg_oauth)`.

### Merge (account merge)
Если юзер сначала зашёл через magic_link на API (создан account A), потом начал писать боту (создан account B) — мы автоматически связать не можем (Telegram не отдаёт email).

После того как пользователь привязывает email в боте (через magic_link на тот же email, что у account A):
1. Детектим коллизию — два аккаунта с identity на один email.
2. Если у обоих есть `natal_profile` — спрашиваем юзера: «У вас профили в обоих аккаунтах. Чей оставить? [бот] / [email] / [ввести новые]».
3. Если конфликта профилей нет — мерджим молча.
4. Мерж: переносим `natal_profile` (по выбору), `requests`, `payments`, `account_subscriptions`, `account_packages`, `tenant_roles`, `account_identities` из source-аккаунта в target. Пересчитываем `account_balance`. `audit_log` записывает full snapshot обоих аккаунтов до мержа для возможного отката.

### JWT
- Access token, 1 час, HS256 или RS256.
- Claims: `sub=account_id, tid=tenant_id|null, sa=bool, roles={tenant_id: [roles]}, exp, iat, jti`.
- Refresh token, 30 дней, хранится в `account_refresh_tokens` (hash), revocable.

### Authorization helpers
```python
def require_superadmin(account=Depends(current_account)): ...
def require_tenant_role(tenant_id: int, roles: tuple[str, ...] = ("owner",)): ...
def require_authenticated(account=Depends(current_account)): ...
```

### Bot token security
- Шифруется AES-GCM с ключом из env `BOT_TOKEN_ENC_KEY`. Decrypt только в `bot-worker` и `task-worker` процессах. `api` процесс не имеет прав на расшифровку (использует только `webhook_secret_path` для роутинга).

## 6. Domain — Blueprint generation

### Portирование астрологического движка

Источник: `/home/ipu/code/work/astrology/src/` (TypeScript/Bun).

| TS-модуль | Python-путь | Замечания |
|---|---|---|
| `astro.ts` | `quantuum/astrology/astro.py` | `astronomy-engine` (Python port доступен в pip) |
| `numerology.ts` | `quantuum/astrology/numerology.py` | чистая арифметика |
| `chinese.ts` (BaZi) | `quantuum/astrology/chinese.py` | `lunar-typescript` → ручная реализация или `lunardate` |
| `humandesign.ts` | `quantuum/astrology/human_design.py` | сложная логика, обязательны fixture-тесты |
| `genekeys.ts` | `quantuum/astrology/gene_keys.py` | поверх human_design |
| `mayan.ts` | `quantuum/astrology/mayan.py` | простой Tzolkin |
| `util.ts` | `quantuum/astrology/util.py` | константы, форматтеры |
| `blueprint.ts` | `quantuum/astrology/blueprint.py` | оркестрация → `calc_md: str` |
| `llm-blueprint.ts` | `quantuum/llm/blueprint_polish.py` | вход `calc_md`, выход `llm_md` |

**Валидация порта:** все 4 фикстуры из `astrology/examples/` (`anna.json`, `nikita.json`, `regina.json`, `victoria.json`) прогоняются через TS-эталон → получаем reference markdown'ы. Python-имплементация в тестах должна выдавать **посимвольно** совпадающий `calc_md`. Это якорь качества миграции.

### LLM client

```python
class LLMClient(Protocol):
    async def complete(
        self, *, system: str, user: str, model: str,
        max_tokens: int, temperature: float
    ) -> CompletionResult: ...

# Реализации в MVP
class AnthropicClient(LLMClient): ...   # default
class OpenAIClient(LLMClient): ...      # backup option
```

- Провайдер выбирается через `LLM_PROVIDER` env / `platform_config.llm.provider`.
- Модель и параметры — `platform_config.llm.{model, temperature, max_tokens}`.
- Тенант может override `llm.model` и `llm.temperature` в пределах `platform_config.llm.tenant_allowed_models` (список) и `llm.tenant_temperature_range = [min, max]`.
- Промпт `prompt.txt` переносится в `src/quantuum/llm/prompts/blueprint_writer.txt`.

### Generation flow

1. Триггер: `/blueprint` в боте или `POST /v1/me/blueprints` в API.
2. **Гейты:**
   - `natal_profile` существует (иначе onboarding запрашивает данные).
   - Квота доступна (`consume_quota` ниже).
3. Атомарно (одна транзакция):
   - `INSERT requests(kind='blueprint', status='pending')`
   - `INSERT blueprints(status='pending', natal_profile_id, ...)`
   - `consume_quota(account_id, kind='blueprint')` — обновляет `account_balance`
4. Enqueue `arq.blueprint_generate(blueprint_id)`, ответить юзеру «Генерирую, ~1 минута…».
5. **Воркер:**
   - Грузит blueprint, natal_profile, tenant_config (LLM-параметры).
   - `calculator(natal_profile) → calc_md` (детерминированно, секунды). Пишем в `blueprints.calc_md`, статус `calculating → generating`.
   - `llm_client.complete(system=prompt, user=calc_md, ...) → llm_md`. Пишем `llm_md`, `tokens_in/out`, `llm_model`, статус `done`.
   - `requests.status = 'done', completed_at = now()`.
   - Доставка: `bot.send_message(chat_id, llm_md[:500] + '... (продолжение в файле)')` + `bot.send_document(chat_id, InputFile(llm_md.encode()))`.
   - На ошибке: статусы → `failed`, **возврат квоты** (`refund_quota`), сообщение юзеру «не получилось, баланс возвращён».

### consume_quota / refund_quota

```python
async def consume_quota(account_id, kind, *, conn) -> Literal["trial","subscription","package"]:
    # SELECT FOR UPDATE on account_balance
    bal = await load_balance_for_update(account_id, conn)
    if not bal.free_trial_used and kind == "blueprint":
        bal.free_trial_used = True
        return "trial"
    if bal.subscription_active_until and bal.subscription_active_until > now():
        return "subscription"
    if bal.package_credits >= 1:
        bal.package_credits -= 1
        # decrement specific package row (oldest expiring first)
        await decrement_oldest_package(account_id, conn)
        return "package"
    raise InsufficientFundsError
```

Reverse через `refund_quota(request_id)`, идемпотентно (записывает в `requests.charged_against = 'none'` после возврата).

### i18n

```python
async def t(key: str, lang: str, *, tenant_id: int, default: str | None = None, **vars) -> str:
    # 1. tenant_string_overrides(tenant_id, key, lang)
    # 2. platform_strings(key, lang)
    # 3. tenant_string_overrides(tenant_id, key, tenant_default_lang)
    # 4. platform_strings(key, tenant_default_lang)
    # 5. default arg
    # 6. f"[missing: {key}]" + warning log
```

- Кеш: Redis hash `i18n:{tenant_id}:{lang}` с TTL 1 час, инвалидируется на pub/sub `i18n_invalidate` при правке через admin API.
- Язык юзера: `accounts.preferred_lang` → `tg_user.language_code` → `tenant_languages.is_default`.
- Если запрошенный язык не в `tenant_languages.enabled` — fallback на дефолт тенанта.

## 7. Payments & franchise tiers

### Provider abstraction

```python
class PaymentProvider(Protocol):
    kind: Literal["tg_stars", "cloudpayments", "cryptobot"]

    async def create_invoice(
        self, *, account_id: int, tenant_id: int,
        plan_kind: Literal["subscription", "package"], plan_id: int,
        amount_cents: int, currency: str, metadata: dict,
    ) -> Invoice: ...

    async def verify_callback(self, body: bytes, headers: dict) -> PaymentEvent: ...

    async def refund(self, payment_id: int) -> RefundResult: ...
```

В MVP реализуется только `TgStarsProvider`.

### Franchise tiers

| Tier | `payment_providers` row | Куда уходят деньги |
|---|---|---|
| Basic | `tenant_id = platform-tenant`, kind=tg_stars | На бот платформы |
| VIP | `tenant_id = owner-tenant`, kind=tg_stars (+ другие, когда добавим) | На бот овнера |

В MVP активен только Basic, и первый тенант = сам `platform-tenant` (его бот собирает Stars). VIP-флоу с лицензией не активирован.

### Stars + Basic для других тенантов (будущая итерация)

Stars привязаны к боту-приёмнику; для Basic-тенанта (бот овнера, деньги платформе) есть варианты:
- Central billing-bot redirect: при оплате юзер ведётся в платформенный `@quantuum_billing_bot`, инвойс там, потом коллбек кредитует юзера в тенанте.
- Basic = только CloudPayments/CryptoBot (Stars остаётся VIP-only или платформенному тенанту).

Решение откладывается до подключения CloudPayments — в дизайне фиксируется как known constraint.

### Plans

`subscription_plans` и `package_plans` поддерживают `tenant_id NULL` (глобальные) и `tenant_id=X` (кастомные). Тенанту в API выдаётся UNION с приоритетом по `slug` у кастомных. Конкретные цены seed-планов определяются перед запуском суперадмином через `POST /admin/platform/plans`; в bootstrap-сидинг закладывается **структура** (1 monthly subscription + 2 packages: «small» и «large» по request_count), цены — заглушки в `price_cents`, после bootstrap правятся через API.

### Subscription lifecycle

```
account_subscriptions.status: active | grace | expired | cancelled
```

- `ends_at - 3 days`: бот шлёт reminder с invoice-кнопкой («продли подписку»).
- `ends_at` достигнут → `grace` (5 дней доступа).
- После grace → `expired`, `account_balance.subscription_active_until` сбрасывается.
- При оплате продления — `renewed_at = now(), ends_at = ends_at + period`.

Stars не имеет native recurring; каждое продление — отдельный invoice. CloudPayments прикручиваем с native recurring позже (тот же state-machine).

### Package lifecycle

- `account_balance.package_credits` = `SUM(requests_remaining WHERE expires_at IS NULL OR expires_at > now())`.
- Списание: FIFO по `(expires_at NULLS LAST, purchased_at ASC)` — сжигаем то, что скоро протухнет.

### Callback handling

`POST /payments/callback/{provider_kind}`:
1. `verify_callback(body, headers)` — валидация подписи.
2. По `external_id` находим/создаём `payments`-row (идемпотентно).
3. В одной транзакции с advisory lock по `external_id`:
   - `payments.status = 'paid', paid_at = now()`
   - Если subscription: ищем активную/grace подписку с тем же `plan_id` для этого `account_id`. Если есть — продлеваем (`ends_at += period, renewed_at = now()`, статус → `active`). Если нет — создаём новую (`status = 'active', started_at = now(), ends_at = now() + period`). Поддерживаемый инвариант: «не более одной незавершённой подписки на (account_id, plan_id)» — обеспечивается partial unique index `account_subscriptions(account_id, plan_id) WHERE status IN ('active','grace')`.
   - Если package: `INSERT account_packages(...)` всегда новой записью.
   - `recompute_account_balance(account_id)`.

### Payouts (Basic)

В MVP — только таблица `payouts` и endpoint `POST /admin/platform/payouts/calculate` для расчёта за период. Суперадмин руками платит и помечает `PATCH /admin/platform/payouts/{id} { status=paid, external_ref=... }`. Авто-выплаты — позже.

## 8. Master bot & invite-onboarding

В MVP создание тенантов — **по invite-коду от суперадмина** (никакой оплаты лицензии в боте). Платный self-service onboarding — отложен.

### Platform tenant
- Одна запись `tenants(is_platform=true, slug='platform')`.
- Владеет мастер-ботом (`@quantuum_onboarding_bot` или какой выберем).
- Customer-флоу (астрология) у мастер-бота отключены — только онбординг и self-service.

### `tenant_invites` table (см. секцию 4).

### Flow

1. **Суперадмин выписывает invite:**
   - `POST /admin/platform/invites { tier, max_uses, expires_at, preset_* }` → возвращает `code` и deeplink `https://t.me/<master_bot>?start=<code>`.
2. **Owner кликает deeplink** → мастер-бот получает `/start <code>`:
   - Невалид/истёк/исчерпан/revoked → «Приглашение недействительно».
   - Ок → FSM-state `OwnerOnboarding(tier=invite.tier, invite_id=...)`. Если `preset_*` заполнены — предзаполняем.
3. **FSM собирает:** `slug, display_name, telegram_username, description, default_language`.
   - Валидации: `slug` unique, `telegram_username` свободен (`master_bot.get_chat(@...)` → 400/«not found» = свободен).
4. **Подтверждение** — кнопка `[Создать бота]` (без оплаты).
5. **Атомарно:** `tenant_invites.used_count++` (если исчерпан — `status=used`), `INSERT tenants(status=provisioning)`, `INSERT tenant_bots(status=provisioning)`, сохраняем в `tenants` поля `owner_tg_id`, `owner_chat_id` (нужны воркеру для финализации), enqueue `arq.provision_tenant(tenant_id)`.

### `provision_tenant` task

```python
async def provision_tenant(ctx, tenant_id: int):
    tenant = await load_tenant(tenant_id)

    token = await try_programmatic_create(tenant.bot_config)
    if token is None:
        await master_bot.send_message(owner_chat_id, "Программное создание недоступно. ...")
        await set_status(tenant_id, "awaiting_manual_token")
        # FSM мастер-бота ждёт ответ с токеном; см. handler ниже
        return

    await finalize_provisioning(tenant_id, token)

async def finalize_provisioning(tenant_id: int, token: str):
    tenant = await load_tenant(tenant_id)
    # owner_tg_id и owner_chat_id берутся из tenant_invites контекста,
    # сохранённого при /start <code> в мастер-боте, либо из FSM-state.
    bot_info = await Bot(token).get_me()
    await save_bot_token(tenant_id, token, bot_info.id, bot_info.username)
    if tenant.transport == "webhook":
        await Bot(token).set_webhook(f"{API_HOST}/tg/{tenant.webhook_secret_path}")
    else:
        await polling_pool.add(tenant_id)
    await seed_tenant_defaults(tenant_id)
    owner_account_id = await create_owner_account(tenant_id, tenant.owner_tg_id)
    await grant_role(tenant_id, owner_account_id, "owner")
    await set_status(tenant_id, "active")
    await master_bot.send_message(tenant.owner_chat_id, f"Готово! @{bot_info.username}")
```

### Fallback FSM
- Мастер-бот в state `awaiting_manual_token` принимает текстовое сообщение → валидирует как Telegram bot token (`Bot(token).get_me()`).
- При успехе — вызывает `finalize_provisioning(tenant_id, token)`.

### Seed defaults
- `tenant_languages(lang=default_language, enabled=true, is_default=true)`
- `tenant_config` пресеты: `llm.model`, `llm.temperature`, `welcome_message_key`
- Опционально — копирование/sym-linking платформенных строк через override (если нужны).

### Self-service owner commands (мастер-бот)
- `/tenants` — список тенантов owner-а
- `/manage <slug>` — меню: settings / plans / stats / pause / resume / transfer
- `/transfer <slug>` — передача владения

Под капотом — обращения к admin API от имени owner-а. Авторизация: `tg_chat` identity → `tenant_roles(role=owner)`.

## 9. Admin API & stats

### Auth tiers
- Superadmin: `/admin/platform/...` — `is_superadmin = true`.
- Tenant owner/admin: `/admin/tenants/{id}/...` — `tenant_roles(tenant_id=id, role∈allowed)`; superadmin тоже имеет доступ.
- Customer: `/v1/...` — authenticated, scope = `accounts.tenant_id`.

### Endpoint inventory (MVP)

См. полный список в брейншторме секции 7. Краткая структура:

```
/auth/magic/request, /auth/magic/consume
/auth/tg/start, /auth/tg/callback
/auth/link/email, /auth/link/telegram, /auth/merge
/auth/refresh, /auth/logout

/v1/me  (GET, PATCH preferences)
/v1/me/natal-profile  (GET, PUT)
/v1/me/blueprints  (GET, POST)
/v1/me/blueprints/{id}, /v1/me/blueprints/{id}/download
/v1/me/balance, /v1/me/plans, /v1/me/subscriptions (POST), /v1/me/packages (POST)
/v1/me/payments, /v1/me/requests

/admin/tenants/{id}  (GET, PATCH)
/admin/tenants/{id}/bot, /config, /strings, /languages
/admin/tenants/{id}/plans  (CRUD)
/admin/tenants/{id}/accounts  (list, detail, balance PATCH)
/admin/tenants/{id}/blueprints, /requests, /payments
/admin/tenants/{id}/stats
/admin/tenants/{id}/roles  (CRUD; owner-only)
/admin/tenants/{id}/transfer, /pause, /resume

/admin/platform/config, /strings, /superadmins
/admin/platform/plans  (global)
/admin/platform/tenants  (list, suspend, archive)
/admin/platform/invites  (CRUD)
/admin/platform/payouts  (calculate, mark paid)
/admin/platform/stats
/admin/platform/llm  (providers, credentials)
/admin/platform/audit-log

/tg/{webhook_secret_path}
/payments/callback/{provider_kind}

/healthz, /readyz, /metrics
```

### Stats (MVP — все на SQL-агрегациях в реалтайме)

**Per-tenant (`GET /admin/tenants/{id}/stats?period=...`):**
- Active customers (last_seen_at within period)
- Paid customers
- DAU / WAU / MAU
- Requests by kind
- Trial → paid conversion
- Revenue (period), MRR
- LLM costs (tokens × price)

**Platform-wide (`GET /admin/platform/stats?period=...`):**
- Same metrics aggregated + per-tenant breakdown table.
- Onboarding funnel: invites issued / used / active tenants.

Materialized views (`vw_tenant_daily_stats` с почасовым refresh) добавляются когда нагрузка вырастет — фасад внутри admin API переключается без изменения контракта.

### Observability
- `structlog` + JSON во всех процессах.
- `request_id` пропагируется через все процессы (в Redis-очередь и arq tasks как context-поле).
- `audit_log` записывается на каждое мутирующее admin-действие (POST/PUT/PATCH/DELETE).
- Sentry SDK подключаем сразу (включаем через env).
- Health endpoints: `/healthz` (всегда 200, liveness), `/readyz` (DB + Redis ping, readiness).

## 10. Deployment

### docker-compose.yml services
- `api` (FastAPI/uvicorn)
- `bot-worker` (aiogram)
- `task-worker` (arq)
- `postgres` (managed бэкапы вне scope MVP — отдельный cron-снапшот)
- `redis`
- `migration` (one-shot Alembic upgrade head на старте)

### Env vars
```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://redis:6379/0
BOT_TOKEN_ENC_KEY=...          # AES-GCM key, base64
JWT_SIGNING_KEY=...            # HS256 secret или RS256 pem
LLM_PROVIDER=anthropic
LLM_API_KEY=...
LLM_MODEL=claude-...
MASTER_BOT_TOKEN=...           # токен мастер-бота, в env (не в БД, потому что bootstrap-критичен)
API_HOST=https://api.quantuum.example
SMTP_*                         # для magic_link писем
SENTRY_DSN=...                 # optional
```

### Bootstrap
1. `docker-compose up` (миграции в `migration` сервисе).
2. Первый суперадмин — задаётся через env `BOOTSTRAP_SUPERADMIN_EMAIL` (создаётся в startup hook, если БД пустая).
3. `platform-tenant` создаётся в migration / startup hook (`is_platform=true, slug='platform'`).
4. Мастер-бот регистрируется (`MASTER_BOT_TOKEN` → set_webhook на `/tg/{platform_tenant_webhook_secret}` или polling).
5. Дальше суперадмин выписывает invite-ы из admin API.

### Backups (out of scope MVP, но проектируем)
- Daily `pg_dump` снапшот, retention 7 дней.
- Stateful volumes: `postgres-data`, `redis-data`.

## 10.5. Domain abstraction (future-proofing)

Ядро MVP — астрология (Quantuum Blueprint). В будущем платформа может обслуживать другие предметные области (карты Таро, чисто нумерологические отчёты, психологические профили, и т.д.) — иногда даже одновременно с астрологией, для разных тенантов.

Чтобы не переписывать половину системы при смене ядра, выделяем «продуктовые швы» уже сейчас (без отдельного абстрактного слоя в MVP — но с осознанным выбором названий и контрактов):

- **`requests.kind`** — уже общий enum (`blueprint|qa|transit|...`). В будущем `kind = 'tarot_reading'`, `kind = 'numerology_chart'` и т.п. добавляются без миграций структуры.
- **`natal_profiles`** в MVP — астрологический профиль (DOB, время, место). На будущее это «subject profile» — данные на которых строится отчёт. Если ядро сменится: миграция = переименование/расширение под нужный домен. Не закладываем JSONB-«всё в одной колонке» сейчас, потому что для астрологии нужна типизация (`date`, `time`, `numeric` для координат) — но имя `natal_profiles` потом можно переименовать в `subject_profiles` без потери смысла строк.
- **`blueprints`** — конкретная «реализация отчёта». На будущее это `reports`, по одной таблице на тип отчёта (астрологический Blueprint, тарологический расклад, и т.д.). MVP-таблица `blueprints` живёт как «один из вариантов» — добавление `tarot_readings` не ломает контракт `requests`.
- **Calculator** (`quantuum/astrology/blueprint.py:build_blueprint`) — конкретная функция «вход → calc_md». Идея на будущее: оформить как `Calculator(subject) -> calc_md` Protocol; ассоциация «product_kind → Calculator» хранится в коде (registry). В MVP — один calculator, прямой вызов.
- **LLM-промпт** — хранится как файл в `src/quantuum/llm/prompts/{product_kind}_writer.txt`. В MVP только `blueprint_writer.txt`. Селекция промпта по `product_kind` (в дальнейшем).
- **Per-tenant `product_kind`** — на будущее: в `tenants` добавится поле `product_kind` (default `astrology_blueprint`), которое определяет, какой calculator + промпт + меню используются. В MVP — захардкоженный астрологический продукт.

Принцип в MVP: **выбираем нейтральные/расширяемые имена** (`requests`, `consume_quota`, `LLMClient`, `PaymentProvider`), но реализуем под астрологию напрямую без лишних слоёв. Когда понадобится второй домен — добавляем регистры (`CALCULATORS`, `PROMPTS`) и поле `tenants.product_kind`. Переписк ничего, кроме точечного рефакторинга, не требует.

## 11. Open questions / risks

1. **Программное создание Telegram-ботов** — фича, на которую частично завязан onboarding `c`-варианта, требует валидации в момент реализации. Фолбэк через BotFather гарантированно работает; план — стартовать с фолбэка как основного пути и подключить программное создание когда подтвердим доступность.
2. **Stars + Basic для чужих тенантов** — известный constraint, решается отдельной итерацией (central billing-bot или CloudPayments как Basic-валюта).
3. **Новый Telegram OAuth** — если на дату запуска не работает в нужном объёме, блокер для публичного API. Внутри Telegram-бота auth работает без OAuth.
4. **Порт BaZi-логики** — `lunar-typescript` не имеет 1:1 Python-аналога; реализация будет требовать тщательной валидации через фикстуры.
5. **Telegram-лимит сообщений** — Blueprint доставляется как `.md` документ; первичная попытка in-line preview ограничена 4096 символами и срезом по абзацу.
6. **LLM-стоимость на скейле** — стоит мониторить с первого дня через `blueprints.llm_tokens_*`; в админ-статистике вывести как метрику.
7. **Postgres RLS** — отложено. До prod-нагрузки нужно ввести политики или утвердить, что row-level фильтрация в коде достаточна.
8. **Тест-данные для астрологии** — обязательны fixture-тесты на 4 примера из `astrology/examples/` посимвольно (по `calc_md`).

## 12. Out-of-scope reminders

Не делаем в MVP, но архитектура готовит:
- CloudPayments + CryptoBot интеграции (через `PaymentProvider` Protocol).
- MAX + VK ботов (универсальный `Channel` Protocol, обёртка над aiogram — пока единственная реализация).
- Q&A / transit / personal year / compatibility (через `requests.kind` + новые arq tasks).
- VIP-тир end-to-end (таблица `tenant_licenses` уже есть).
- Авто-перевод i18n (новый arq task).
- Web admin UI (admin API уже всё закрывает).
- Web personal cabinet (публичный API уже всё закрывает).
- Materialized views для статистики (фасад уже единый).
