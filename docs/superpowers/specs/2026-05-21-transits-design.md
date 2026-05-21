# Transits («сейчас» + окно вперёд) — Design Spec

**Status:** Approved design (brainstorming). Second sub-project of the §24 "future" feature wave (Q&A → **transits** → compatibility). Compatibility gets its own spec→plan cycle later.

**One-liner:** A forward-looking transit report — given the asker's natal chart, deterministically compute the current sky, the transits currently active against the natal chart, and the exact peak dates of every transit becoming exact within a forward window; then have a grounded LLM narrate it. Delivered via the bot and the public API, billed through the existing quota model.

---

## 1. Goals / non-goals

**Goals**
- Forward-looking transit report: current sky + active transits now + exact peak dates within a window (default 90 days), grounded in the asker's own natal chart.
- Reuse everything already built: the astrology engine (`ecliptic_longitude`, `planet_position`, `ascendant_longitude`, `midheaven_longitude`, `lunar_nodes`, `find_aspect`/`ASPECTS`), the LLM client + DB-backed config, the request/quota/billing ledger, the arq worker, i18n.
- Available on the bot (`/transits` + menu button) and the public API (`POST /v1/me/transits`, `GET`).

**Non-goals (this sub-project)**
- Backward window / "what just happened" (chosen: forward only).
- A broader "now" digest folding in personal-year theme or Moon phase (chosen: transits only).
- Compatibility / synastry (separate sub-project).
- Multi-turn conversation (transits are one-shot reports).
- Per-aspect interpretation lookup tables (the LLM narrates from the computed table).

---

## 2. Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| Window | **Forward window with peak (exact) dates.** Default 90 days; API-configurable, capped 7–180. |
| Report content | **Transits only** (no personal-year/Moon-phase digest). |
| Monetization | Reuse `consume_quota("transit")`: active **subscribers free**, others spend **one package credit** (shared pool with blueprints/qa). **No free trial** for `transit`. |
| Surface | **Bot + public API.** |
| Grounding | LLM narrates from the natal `calc_md` (reused like Q&A) **plus** the deterministically-computed `transit_md`. Requires a `natal_profile`. |
| Execution | **Async via arq** (`transit_generate`), mirroring `qa_generate` — the task-worker is the only process with `llm_client`. |
| Exactness algorithm | **Daily-grid sample + sign-change detection + bisection** (handles retrograde multi-hits). |

---

## 3. Astronomy: the transit computation

New module `quantuum/astrology/transits.py`. **Pure** (no DB), reuses `astro.py`. All times tz-aware UTC.

### 3.1 Configuration constants
```python
# Transiting bodies scanned for the forward forecast. Moon EXCLUDED (≈13°/day → noise);
# it still appears in the "current sky" table and as a natal target.
TRANSIT_FORECAST_BODIES = ("Sun","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")

# "Current sky" snapshot includes all ten (ALL_PLANETS order from blueprint.py).
CURRENT_SKY_BODIES = ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")

# Natal points used as aspect targets (mirrors the blueprint aspect grid: planets + Asc + MC + NN).
NATAL_TARGETS = ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto","Asc","MC","NN")

# Major aspects only, with TIGHT transit orbs (minor aspects excluded as forecast noise).
# Insertion order = tie-break priority (strongest/most-common first), matching astro.ASPECTS style.
TRANSIT_ASPECTS = {
    "Conjunction": {"angle": 0,   "orb": 3.0},
    "Opposition":  {"angle": 180, "orb": 3.0},
    "Trine":       {"angle": 120, "orb": 3.0},
    "Square":      {"angle": 90,  "orb": 3.0},
    "Sextile":     {"angle": 60,  "orb": 2.0},
}

GRID_STEP_HOURS = 24          # daily sampling grid
BISECTION_ITERS = 40          # ~ minute precision over a 1-day bracket
DEFAULT_WINDOW_DAYS = 90
MIN_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 180
```

### 3.2 Natal targets (fixed longitudes)
```python
def compute_natal_targets(inp: BlueprintInput) -> dict[str, float]:
    """Natal ecliptic longitudes for every NATAL_TARGETS point, computed from the
    birth instant + location. Reuses astro.py exactly as build_blueprint does."""
    birth = parse_birth_instant(inp)
    out = {p: planet_position(p, birth).longitude for p in ALL_PLANETS}
    out["Asc"] = ascendant_longitude(birth, inp.latitude, inp.longitude)
    out["MC"]  = midheaven_longitude(birth, inp.longitude)
    out["NN"]  = lunar_nodes(birth)["north"].longitude
    return out
```
Natal longitudes are **fixed** for the whole window (the natal chart does not move).

### 3.3 Signed separation and the crossing function
For a transiting longitude `t_lon` and a fixed natal longitude `n_lon`, the angular separation folded to `0..180`:
```python
def _sep180(a: float, b: float) -> float:
    return abs(((a - b + 540) % 360) - 180)   # 0..180, same convention as astro.find_aspect
```
A transit of `aspect` (angle θ) to a natal point is **exact** when `_sep180(t_lon, n_lon) == θ`. Define the smooth crossing function per (body, target, aspect):
```python
f(dt) = _sep180(ecliptic_longitude(body, dt), n_lon) - θ
```
`f` is continuous away from the fold; an exact transit is a zero of `f`. Across the daily grid a sign change of `f` between two adjacent samples brackets a zero. Bisection on that bracket yields the exact instant.

> **Fold guard:** `_sep180` has corners at 0° and 180° (where the derivative flips sign). For θ=0 (Conjunction) and θ=180 (Opposition), `f` touches zero from one side rather than changing sign at the true minimum. To catch those, ALSO detect a **local minimum of `f`** between three consecutive grid samples that dips at/below 0 within orb, and bisect each side of the minimum. Concretely: detect (a) sign changes for all aspects, and (b) for conjunction/opposition, local minima of `_sep180−θ` that go ≤ 0. This reliably captures exact hits including stationary/retrograde turns.

### 3.4 Algorithm (single pass, reuse samples)
```python
@dataclass(frozen=True)
class TransitHit:
    body: str            # transiting body
    target: str          # natal point
    aspect: str          # aspect name
    exact_at: datetime   # UTC instant of exactness (bisected)
    retrograde: bool     # transiting body retrograde at exact_at

@dataclass(frozen=True)
class ActiveAspect:
    body: str
    target: str
    aspect: str
    orb: float           # current |sep - angle|, degrees
    applying: bool       # orb shrinking (vs +6h)
    exact_at: datetime | None   # nearest exact within window, if any

@dataclass(frozen=True)
class SkyPosition:
    body: str
    longitude: float
    sign: str            # to_sign_degree(...).sign
    retrograde: bool

@dataclass(frozen=True)
class TransitReport:
    as_of: datetime
    window_days: int
    sky: list[SkyPosition]            # CURRENT_SKY_BODIES at as_of
    active: list[ActiveAspect]        # aspects within orb at as_of (sorted: applying first, then orb asc)
    upcoming: list[TransitHit]        # all exact hits with exact_at > as_of, sorted by exact_at
```

`compute_transits(inp, *, as_of, window_days)`:
1. `natal = compute_natal_targets(inp)`.
2. `sky` = `planet_position(b, as_of)` for each `CURRENT_SKY_BODIES` body → `SkyPosition`.
3. **Grid:** sample each `TRANSIT_FORECAST_BODIES` longitude at `as_of + k*GRID_STEP_HOURS` for `k = 0 .. ceil(window_days*24/GRID_STEP_HOURS)` (one extra step past the window edge so the last day's bracket is closed). Cache as `lon[body][k]`. This is the only place `ecliptic_longitude` is called in bulk (≈9×91 ≈ 820 evals).
4. **Hits:** for each (body, target, aspect): walk the grid, for each adjacent pair detect sign-change of `f` (and conj/opp local-minimum-≤0); bisect each bracket (`BISECTION_ITERS`) to `exact_at`; keep hits with `as_of < exact_at <= as_of + window_days`. Retrograde flag from sign of `ecliptic_longitude(body, exact_at+6h) - ecliptic_longitude(body, exact_at)`.
5. **Active now:** for each (forecast body, target), compute `sep = _sep180(lon_now, n_lon)`; for each aspect with `|sep-angle| <= orb`, take the strongest (smallest `|sep-angle|`, insertion-order tie-break — same rule as `find_aspect`); `applying` by comparing `|sep-angle|` now vs at `as_of+6h`; `exact_at` = nearest hit for that (body,target,aspect) within the window (may be None if the exact already passed before `as_of`).
6. Return `TransitReport` with `active` sorted (applying first, then orb asc) and `upcoming` sorted by `exact_at`.

### 3.5 Deterministic markdown — `render_transits_md(report) -> str`
Three sections (Markdown tables; degrees via `to_sign_degree`/`fmt`-style formatting consistent with `blueprint.py`):
- **Current sky** — `Body | Position | Retrograde` for `CURRENT_SKY_BODIES`.
- **Active transits now** — `Transit | Aspect | Natal | Orb | Applying/Separating | Exact` (date or `—`). Empty → `_No transits within orb right now._`
- **Upcoming exact transits (next N days)** — `Date | Transit | Aspect | Natal | ℞?`, sorted by date. Empty → `_No exact transits in the window._`

This text is stored in `transit_reports.transit_md` and fed to the LLM. It is fully deterministic given `(inp, as_of, window_days)`.

---

## 4. Data model

New table (mirrors `qa_answers` shape):
```
transit_reports
  id               PK
  tenant_id        FK tenants.id        (index)
  account_id       FK accounts.id       (index)
  natal_profile_id FK natal_profiles.id
  blueprint_id     FK blueprints.id, nullable   -- natal calc_md source used for grounding, if any
  as_of            timestamptz, nullable -- the "now" the report was computed for (set by the task at generation)
  window_days      int                  -- forward window used (set at creation)
  transit_md       text, nullable       -- deterministic computed tables (stored for reproducibility)
  report_md        text, nullable       -- LLM narration
  lang             text                 -- answer language (resolved from the asker)
  status           text  default 'pending'   -- pending|generating|done|failed
  error            text, nullable
  llm_provider     text, nullable
  llm_model        text, nullable
  llm_tokens_in    int,  nullable
  llm_tokens_out   int,  nullable
  created_at       timestamptz
  completed_at     timestamptz, nullable
  __table_args__: Index("ix_transit_reports_tenant_created", tenant_id, created_at)
```
New Alembic migration; `down_revision = b7c8d9e0f1a2` (current head). Declare the index in `__table_args__` so the test DB (`create_all`) enforces it. Single linear head.

The generic ledger row: `Request(kind="transit", reference_id=report.id, reference_type="transit", charged_against=<result of consume_quota>)`.

---

## 5. Components & data flow

### Domain — `quantuum/domain/transits.py`
- `create_transit(session, *, tenant_id, account_id, natal_profile_id, window_days, lang) -> TransitReport` — insert pending row (stores `window_days`; `as_of` set by the task at compute time so it reflects the actual generation moment).
- `get_transit(session, report_id) -> TransitReport` (raises `NotFoundError`).
- `list_transits(session, *, account_id, limit, offset)` — newest first.
- `set_transit_status(session, report_id, status, **fields)` — mirror `set_qa_status` (sets `completed_at` on terminal states).
- `resolve_natal(session, *, account_id, natal_profile_id) -> tuple[BlueprintInput, str, int | None]` — returns `(blueprint_input, natal_calc_md, blueprint_id | None)`:
  - load the `NatalProfile` (raise `NotFoundError` if missing); `inp = from_natal_profile(profile)`.
  - reuse the latest **done** `Blueprint.calc_md` (+ its id) for grounding if present; else `build_blueprint(inp)` and `blueprint_id=None`.
  - (The numeric natal targets come from `inp` via `compute_natal_targets`, not from the markdown.)

### LLM — `quantuum/llm/transit_report.py` + `prompts/transit_astrologer.txt`
- `transit_astrologer.txt` (system prompt): a grounded transit astrologer. Rules: narrate using **only** facts present in the provided natal chart markdown and the computed transit tables; never invent or alter placements, aspects, dates, or numbers; explain what the active and upcoming transits mean for the person, concretely and practically; lead with the most significant (tightest/slow-planet) transits; note exact dates when given; if the tables are empty, say the sky is quiet for them right now; answer in the **same language as requested** (`lang`); concise, warm, practical; Markdown only; no process notes.
- `async def transit_report(client, natal_md, transit_md, *, lang, model, temperature, max_tokens) -> LLMResult` — `user = "\n".join(["Write a transit reading for this person using ONLY the natal chart and the computed transit tables below.", f"Answer in language: {lang}.", "", "NATAL CHART:", natal_md, "", "TRANSITS:", transit_md])`; `client.complete(system=<prompt>, user=user, model=, temperature=, max_tokens=)`.

### Task — `quantuum/tasks/transits.py: transit_generate(ctx, report_id, chat_id=None, request_id=None)`
Mirror `qa_generate` exactly:
1. Load report. `inp, natal_md, blueprint_id = resolve_natal(...)`. `as_of = utcnow()`. `report = compute_transits(inp, as_of=as_of, window_days=report.window_days)`; `transit_md = render_transits_md(report)`. `set_transit_status(generating, blueprint_id=blueprint_id, as_of=as_of, transit_md=transit_md)`.
2. `llm_client = ctx.get("llm_client")`. **If None → fail + refund** (no meaningful no-LLM narration): `set_transit_status(failed, error="llm unavailable")`, `refund_quota(request_id)`, return.
3. `cfg = await get_llm_config(session)`; `result = await transit_report(llm_client, natal_md, transit_md, lang=report.lang or FALLBACK_LANG, model=cfg["model"], temperature=cfg["temperature"], max_tokens=cfg["max_tokens"])`. `set_transit_status(done, report_md=result.text, llm_provider=cfg["provider"], llm_model=result.model, llm_tokens_in=..., llm_tokens_out=...)`.
4. `complete_request(request_id, reference_id=report_id, reference_type="transit")` (own try, never refunds — same nuance as qa).
5. On exception → `failed` + `refund_quota`, return.
6. Delivery (best-effort, outside the session, no refund): `bot.send_message(chat_id, report_md[:4000])`; if longer, also `send_document(BufferedInputFile(report_md.encode(), "transits.md"))`.

Register `transit_generate` in `tasks/worker.py functions`. `enqueue_transit(report_id, chat_id, request_id)` in `tasks/enqueue.py` (mirror `enqueue_qa`).

### Bot — `quantuum/bot/handlers/transits.py`
- `/transits [window_days]` (Command) and a menu button "🌌 Транзиты" / "🌌 Transits" → run immediately with default window (no FSM prompt needed; window is optional).
- Optional inline `window_days` arg parsed and clamped to `[MIN_WINDOW_DAYS, MAX_WINDOW_DAYS]`; invalid → default.
- Require a `natal_profile` (else `transit.no_profile`).
- `consume_quota(account_id, "transit")` → `InsufficientFundsError` → reply `transit.no_quota` + the existing buy-offer keyboard (reuse `_buy_offer_kb` from generate.py). Else: `create_request(kind="transit", charged_against=result)` + `create_transit(pending, window_days=...)` + `enqueue_transit(report.id, chat_id, request.id)` → reply `transit.thinking`.
- Register `transits.router` on the customer dispatcher (`bot/app.py`), after `qa.router`. (Master bot unaffected.)
- Menu: add `btn.transits` → `MENU_BUTTON_KEYS = ("btn.generate","btn.ask","btn.transits","btn.profile","btn.history","btn.help")` (6 buttons); `main_menu_kb` layout `adjust(2,2,2)`. Route the new button text in `menu.py`.
- All strings via the injected `i18n`.

### API — `quantuum/api/routes/me.py`
- `POST /v1/me/transits {window_days?}` (auth = customer) → require natal_profile (404 if none), clamp `window_days` to `[MIN,MAX]` (default 90), `consume_quota` (402 `InsufficientFundsError`), create request + transit, enqueue → `202 {id, status:"pending"}`; on enqueue failure → refund + 503.
- `GET /v1/me/transits/{id}` → detail (report when done); 404 if not the caller's.
- `GET /v1/me/transits?limit=&offset=` → history (caller's, newest first).
- Schemas: `TransitCreateIn(window_days: int | None)`, `TransitCreatedOut(id, status)`, `TransitOut(id, window_days, as_of, report_md, status, lang, created_at, completed_at)`.

---

## 6. i18n
New `transit.*` keys in `BASE_STRINGS` (ru + en): `transit.no_profile`, `transit.no_quota`, `transit.thinking`, `transit.failed`, plus `btn.transits`. The report body itself is produced by the LLM in the requested language (not a seeded string). The deterministic `transit_md` table headers are internal grounding text (English, not user-facing) — the user only ever sees the LLM narration.

---

## 7. Error handling
- LLM failure / no `llm_client` → `transit_reports.status="failed"` + `refund_quota` (the asker is not charged).
- Delivery failure (bot) → logged, **no** refund (the report is stored; the user can fetch via API/history).
- `complete_request` wrapped so a bookkeeping failure can't trigger a refund of a successful report.
- Missing natal_profile → handled before quota is consumed (no charge).
- `compute_transits` is pure/deterministic; any exception there occurs inside the task's try → `failed` + refund.

## 8. Testing
- **astrology/transits**:
  - `compute_natal_targets` returns all 13 targets and matches `build_blueprint`'s underlying longitudes for a fixture birth.
  - Exact-date finding: for a constructed case (e.g. transiting Sun reaching a known natal longitude) the bisected `exact_at` lands within a tight tolerance (≤ a few minutes) of an independently sampled minimum.
  - Retrograde multi-hit: a slow planet stationing near a natal point yields multiple `TransitHit`s (assert >1 within a window that brackets a retrograde loop).
  - Conjunction/opposition fold: a conjunction whose `_sep180` only touches 0 (no sign change) is still captured via the local-minimum path.
  - `active`: a near-exact pair shows up in `active` with correct `applying` and small `orb`; orbs outside `TRANSIT_ASPECTS` orb are excluded.
  - `render_transits_md`: empty-section placeholders; non-empty tables contain the expected rows; deterministic for fixed `(inp, as_of, window_days)`.
- **llm/transit_report**: with a fake client, asserts the prompt is loaded and the user message wraps natal_md + transit_md + the lang line.
- **domain/transits**: create/get/list/status; `resolve_natal` reuses a done blueprint's calc_md when present (blueprint_id set) else builds (blueprint_id None); NotFoundError when profile missing.
- **task/transit_generate**: mocked llm_client → report stored + tokens + delivered + `transit_md`/`as_of` persisted; exception → failed + refund; `llm_client=None` → failed + refund; `complete_request` failure does NOT refund a successful report.
- **bot/transits**: `/transits` happy path (quota consumed, report+request created, enqueued, "thinking" reply); `/transits 30` clamps/uses window; no-quota → buy offer; no-profile → prompt; menu button routes.
- **api/transits**: POST 202 + GET detail + list; 402 on no quota; 404 cross-account; `window_days` clamp; 503+refund on enqueue failure.
- **ui keyboards**: `main_menu_kb` now has 6 localised buttons incl. `btn.transits` (ru + en) — update existing menu tests.
- **migration**: one migration; `alembic heads` single linear head; validate via `--sql` (live app DB may be unreachable — see the app-db memory).

## 9. Deploy notes
- `alembic upgrade head` for `transit_reports`.
- `LLM_API_KEY` is **required** for transits to work (no degraded fallback, like Q&A).
- New bot strings auto-seed via `ensure_base_strings`.
- Register `transit_generate` in the task-worker (rebuild image); register `transits.router` on the customer bot dispatcher.

## 10. Future (out of scope here)
- Backward window ("what just happened") — the grid scan trivially extends to `as_of - k`.
- "Now" digest: fold in personal-year theme (already computed in numerology) + Moon phase.
- Subscriber transit push (feeds naturally into feature wave 3/3 daily push — the daily push can reuse `compute_transits`).
- Per-aspect interpretation tables / configurable orb sets per tenant.
- Compatibility / synastry (cross-aspects between two natal charts) — separate sub-project.
