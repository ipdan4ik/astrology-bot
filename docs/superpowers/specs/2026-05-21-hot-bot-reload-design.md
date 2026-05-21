# Hot Bot Reload — Design Spec

**Date:** 2026-05-21
**Status:** Approved (ready for implementation plan)

## Goal

Newly-provisioned (and deactivated) tenant bots start/stop serving in the running
polling and webhook workers **without a process restart**. Today a new customer bot
only comes alive after the bot worker is restarted, because the bot pools are built
once at startup.

## Background — current architecture

Multi-tenant Telegram bot SaaS. Each tenant has one `TenantBot` row (encrypted token,
`bot_telegram_id`, `transport` of `"polling"` or `"webhook"`, `status`). Two worker
entrypoints serve bots:

- **Polling** (`src/quantuum/bot/polling.py`): builds `customer_pool` / `master_pool`
  via `build_bots(...)` once, then calls `dp.start_polling(*pool.values())` over a
  **fixed** set. New bots are not polled until restart.
- **Webhook** (`src/quantuum/bot/runner.py`): a loop that `pop_update()`s envelopes
  `{bot_id, update}` from Redis and routes via `customer_pool` / `master_pool` dicts
  built **once** at startup. An update for an unknown bot logs `update_for_unknown_bot`
  and is dropped.

Master vs customer split is by `tenant.is_platform` (platform tenant → master
dispatcher with onboarding handlers; everyone else → customer dispatcher).

Ingestion is already DB-driven and needs no change: the webhook HTTP endpoint
(`api/routes/webhook.py`) looks up the bot by secret per-request, and task delivery
(`tasks/delivery.py`) resolves the owning tenant bot per-reading. The only remaining
static in-memory state is the two runners' pools. Those are what this feature makes
dynamic.

## Approach

A shared **reconcile** mechanism diffs the DB's set of active bots (for a transport)
against the currently-live pool and applies the delta. It is driven by a single loop
that fires on **either** a periodic timeout (~10s, self-healing baseline) **or** a
Redis pub/sub nudge published at provisioning (instant, <1s). Both transports use the
same core; they differ only in how a bot is added/removed (mutate a dict vs.
spawn/cancel a poll task).

## Components

### New module: `src/quantuum/bot/reload.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class BotSpec:
    bot_telegram_id: int
    token: str          # decrypted bot token
    is_master: bool     # platform tenant => master dispatcher


async def load_active_bot_specs(session, transport: str) -> dict[int, BotSpec]:
    """All active tenant bots for `transport`, keyed by bot_telegram_id.

    Joins TenantBot (status="active", transport=transport, bot_telegram_id not null)
    to Tenant to determine is_master (tenant.is_platform). Token decrypted via
    decrypt_token. Rows with empty token or null bot_telegram_id are skipped.
    """


def diff_specs(
    current_ids: set[int], desired: dict[int, BotSpec]
) -> tuple[set[int], set[int]]:
    """Return (to_add, to_remove) bot ids. Pure."""
    return set(desired) - current_ids, current_ids - set(desired)
```

### Trigger: Redis pub/sub — `src/quantuum/redis_client.py`

```python
BOT_RELOAD_CHANNEL = "bot:reload"

async def publish_bot_reload() -> None:
    await get_redis().publish(BOT_RELOAD_CHANNEL, "1")
```

Unified periodic + nudge loop, also in `reload.py` (depends on redis_client):

```python
async def reload_signals(interval: float):
    """Yield once per nudge OR per `interval` seconds, whichever comes first.

    Subscribes to BOT_RELOAD_CHANNEL. Each yield drives one reconcile, so a missed
    nudge is still corrected within `interval` (self-healing). Coalescing extra
    nudges into one or two redundant reconciles is harmless.
    """
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(BOT_RELOAD_CHANNEL)
    try:
        while True:
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=interval)
            yield
    finally:
        await pubsub.unsubscribe(BOT_RELOAD_CHANNEL)
        await pubsub.aclose()
```

### Publish site — `src/quantuum/bot/handlers/master_onboarding.py`

After a successful `finalize_provisioning` in **both** completion paths
(`on_managed_bot_created` and `on_manual_token`), call `await publish_bot_reload()`
so the customer polling/webhook worker picks up the new bot immediately. (The same
channel will later serve deactivation; out of scope here.)

### Webhook runner — `src/quantuum/bot/runner.py`

Add to `WebhookConsumer`:

```python
async def reconcile(self) -> None:
    async with self.sessionmaker() as session:
        desired = await load_active_bot_specs(session, "webhook")
    live = set(self.customer_pool) | set(self.master_pool)
    to_add, to_remove = diff_specs(live, desired)
    for bot_id in to_add:
        spec = desired[bot_id]
        bot = Bot(token=spec.token)
        (self.master_pool if spec.is_master else self.customer_pool)[bot_id] = bot
    for bot_id in to_remove:
        bot = self.customer_pool.pop(bot_id, None) or self.master_pool.pop(bot_id, None)
        if bot is not None:
            await bot.session.close()
```

`run()` starts the consumer with **empty** pools (replacing the old build-once-at-startup),
`await consumer.reconcile()` once for the immediate initial load, then launches a background
task `async for _ in reload_signals(interval): await consumer.reconcile()` via
`asyncio.create_task`, and continues its existing `pop_update` loop. The `pop_update` loop is
otherwise unchanged and reads the pools live. Both run on the same event loop (no locking
needed; dict ops are atomic and reconcile awaits only for the DB read).

`WebhookConsumer.__init__` gains a `sessionmaker` so reconcile can open sessions.

### Polling runner — `src/quantuum/bot/polling.py` (approach A: per-bot poll tasks)

A supervisor keeps one `asyncio.Task` per bot running a manual long-poll loop, reusing
the **same** customer/master dispatchers so in-progress FSM state is preserved and
existing bots are never interrupted.

```python
async def poll_one(dp, bot, allowed_updates) -> None:
    """Long-poll a single bot, feeding updates into `dp`. Resilient to transient errors."""
    await bot.delete_webhook(drop_pending_updates=True)
    offset = None
    while True:
        try:
            updates = await bot.get_updates(
                offset=offset, timeout=30, allowed_updates=allowed_updates
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("poll_error", bot_id=bot.id)
            await asyncio.sleep(3)
            continue
        for u in updates:
            offset = u.update_id + 1
            await dp.feed_update(bot, u)


class PollingSupervisor:
    def __init__(self, sessionmaker, customer_dp, master_dp, *, spawn=None):
        self.sessionmaker = sessionmaker
        self.customer_dp = customer_dp
        self.master_dp = master_dp
        self.live: dict[int, tuple[Bot, asyncio.Task]] = {}
        # `spawn` is injectable for tests (default starts a real poll_one task).
        self._spawn = spawn or self._default_spawn

    def _default_spawn(self, spec: BotSpec) -> tuple[Bot, asyncio.Task]:
        bot = Bot(token=spec.token)
        dp = self.master_dp if spec.is_master else self.customer_dp
        allowed = dp.resolve_used_update_types()
        return bot, asyncio.create_task(poll_one(dp, bot, allowed))

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            desired = await load_active_bot_specs(session, "polling")
        to_add, to_remove = diff_specs(set(self.live), desired)
        for bot_id in to_add:
            self.live[bot_id] = self._spawn(desired[bot_id])
        for bot_id in to_remove:
            bot, task = self.live.pop(bot_id)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await bot.session.close()
```

`run()`: bootstrap (existing `ensure_*` calls), create the two dispatchers once, build a
`PollingSupervisor`, `await supervisor.reconcile()` once for the initial set, then
`async for _ in reload_signals(interval): await supervisor.reconcile()`.

### Config — `src/quantuum/settings.py`

`bot_reload_interval_seconds: float = 10.0`.

## Error handling

- A reconcile that fails (e.g. DB blip) is logged and the loop continues; the next
  signal retries — no worker death.
- `poll_one` catches per-iteration errors, logs, backs off 3s, continues. A persistently
  bad token just produces repeating logged errors for that one bot.
- Removed bots always have their aiogram session closed (both transports).
- `reload_signals` cleans up its pubsub subscription on exit.

## Testing (TDD)

- `diff_specs` — pure set math: add-only, remove-only, mixed, no-op.
- `load_active_bot_specs` — seed active/inactive bots across a customer tenant and the
  platform tenant; assert keys, decrypted token, `is_master`, and that inactive /
  tokenless / wrong-transport rows are excluded.
- Webhook `WebhookConsumer.reconcile` — seed a new active webhook bot, reconcile, assert
  it lands in the right pool; deactivate it, reconcile, assert removed and session
  closed. Use a fake/closed Bot to avoid network.
- Polling `PollingSupervisor.reconcile` — inject a fake `spawn` returning a sentinel
  (Bot stub + dummy task); assert spawn called for to_add ids and the task is cancelled
  + popped for to_remove ids. No real network or polling.
- `reload_signals` — against the test Redis: publishing to the channel yields a tick;
  with no publish, the interval timeout yields a tick. Bound the test with a short
  interval and a timeout guard.
- Publish-on-finalize — in the master-onboarding handler tests, monkeypatch
  `publish_bot_reload` and assert it is awaited after `finalize_provisioning` in both
  the managed and manual paths.

## Files

| File | Change |
|------|--------|
| `src/quantuum/bot/reload.py` | **new** — `BotSpec`, `load_active_bot_specs`, `diff_specs`, `reload_signals`, `poll_one`, `PollingSupervisor` |
| `src/quantuum/redis_client.py` | add `BOT_RELOAD_CHANNEL`, `publish_bot_reload` |
| `src/quantuum/bot/runner.py` | `WebhookConsumer` gains `sessionmaker` + `reconcile`; `run()` adds reconcile loop |
| `src/quantuum/bot/polling.py` | `run()` switches to `PollingSupervisor` + reconcile loop |
| `src/quantuum/bot/handlers/master_onboarding.py` | publish reload after `finalize_provisioning` (both paths) |
| `src/quantuum/settings.py` | `bot_reload_interval_seconds` |
| `tests/test_bot_reload.py` | **new** — diff/specs/reconcile/signals tests |
| `tests/test_master_onboarding.py` | assert publish-on-finalize (both paths) |

## Out of scope

- Registering Telegram `set_webhook` for a new webhook bot (a provisioning concern;
  current bots default to `transport="polling"`).
- Deactivation/suspension UX (the `bot:reload` channel is reused later for it).
- Hot-reloading code/handlers (this is bot-set reload, not code reload).
