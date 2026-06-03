from sqlmodel import select

from quantuum.astrology.transits import clamp_window
from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.db.models import Blueprint, NatalProfile, TransitReport

_TERMINAL = {"done", "failed"}

# Content fields a worker may set alongside status; anything else is rejected.
_STATUS_FIELDS = frozenset({
    "transit_md", "report_md", "lang", "error", "blueprint_id", "as_of",
    "llm_provider", "llm_model", "llm_tokens_in", "llm_tokens_out",
})


async def create_transit(
    session,
    *,
    tenant_id: int,
    account_id: int,
    natal_profile_id: int,
    window_days: int | str | None,  # API passes int|None; bot passes str|None — clamp_window coerces
    lang: str | None,
) -> TransitReport:
    row = TransitReport(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        window_days=clamp_window(window_days),
        lang=lang,
        status="pending",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_transit(session, report_id: int) -> TransitReport:
    row = await session.get(TransitReport, report_id)
    if row is None:
        raise NotFoundError("transit report not found")
    return row


async def list_transits(
    session, *, account_id: int, limit: int = 50, offset: int = 0
) -> list[TransitReport]:
    result = await session.execute(
        select(TransitReport)
        .where(TransitReport.account_id == account_id)
        .order_by(TransitReport.created_at.desc(), TransitReport.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def set_transit_status(session, report_id: int, status: str, **fields) -> None:
    unknown = set(fields) - _STATUS_FIELDS
    if unknown:
        raise ValueError(f"set_transit_status: disallowed fields {sorted(unknown)}")
    row = await get_transit(session, report_id)
    row.status = status
    for key, value in fields.items():
        setattr(row, key, value)
    if status in _TERMINAL:
        row.completed_at = utcnow()
    session.add(row)
    await session.commit()


async def resolve_natal(session, *, account_id: int, natal_profile_id: int):
    """Return (BlueprintInput, natal_calc_md, blueprint_id | None).

    Reuses the latest done Blueprint's calc_md for grounding if present; otherwise
    builds one from the profile. The numeric natal targets come from the
    BlueprintInput (via compute_natal_targets), not from the markdown.
    """
    # Profile is loaded first (unlike qa.py's blueprint-first resolve_calc_md): we
    # always need a BlueprintInput from the profile for the numeric natal targets,
    # regardless of whether a done Blueprint exists. Do not reorder to blueprint-first.
    profile = await session.get(NatalProfile, natal_profile_id)
    if profile is None:
        raise NotFoundError("natal profile not found")

    from quantuum.astrology.blueprint import build_blueprint, from_natal_profile

    inp = from_natal_profile(profile)

    result = await session.execute(
        select(Blueprint)
        .where(
            Blueprint.account_id == account_id,
            Blueprint.status == "done",
            Blueprint.calc_md.is_not(None),
        )
        .order_by(Blueprint.created_at.desc())
        .limit(1)
    )
    bp = result.scalars().first()
    if bp is not None:
        return inp, bp.calc_md, bp.id

    return inp, build_blueprint(inp), None
