from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.db.models import Blueprint, NatalProfile, QaAnswer

_TERMINAL = {"done", "failed"}


async def create_qa(
    session,
    *,
    tenant_id: int,
    account_id: int,
    natal_profile_id: int,
    question: str,
    lang: str | None,
) -> QaAnswer:
    qa = QaAnswer(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        question=question,
        lang=lang,
        status="pending",
    )
    session.add(qa)
    await session.commit()
    await session.refresh(qa)
    return qa


async def get_qa(session, qa_id: int) -> QaAnswer:
    qa = await session.get(QaAnswer, qa_id)
    if qa is None:
        raise NotFoundError("qa not found")
    return qa


async def list_qa(
    session, *, account_id: int, limit: int = 50, offset: int = 0
) -> list[QaAnswer]:
    result = await session.execute(
        select(QaAnswer)
        .where(QaAnswer.account_id == account_id)
        .order_by(QaAnswer.created_at.desc(), QaAnswer.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def set_qa_status(session, qa_id: int, status: str, **fields) -> None:
    qa = await get_qa(session, qa_id)
    qa.status = status
    for key, value in fields.items():
        setattr(qa, key, value)
    if status in _TERMINAL:
        qa.completed_at = utcnow()
    session.add(qa)
    await session.commit()


async def resolve_calc_md(
    session, *, account_id: int, natal_profile_id: int
) -> tuple[str, int | None]:
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
        return bp.calc_md, bp.id

    profile = await session.get(NatalProfile, natal_profile_id)
    if profile is None:
        raise NotFoundError("natal profile not found")

    from quantuum.astrology.blueprint import build_blueprint, from_natal_profile

    return build_blueprint(from_natal_profile(profile)), None
