from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlmodel import select

from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb
from quantuum.bot.ui.keyboards import blueprint_detail_kb, history_list_kb
from quantuum.bot.ui.paging import page_slice
from quantuum.bot.ui.text import render_detail, render_history_label
from quantuum.db.models import Account, Blueprint
from quantuum.db.session import get_sessionmaker
from quantuum.i18n import Translator

router = Router()
PAGE_SIZE = 5


async def fetch_history_window(session, *, account_id: int, page: int) -> list[Blueprint]:
    result = await session.execute(
        select(Blueprint)
        .where(Blueprint.account_id == account_id)
        .order_by(Blueprint.id.desc())
        .offset(page * PAGE_SIZE)
        .limit(PAGE_SIZE + 1)
    )
    return list(result.scalars().all())


async def _render_list(target, account: Account, i18n: Translator, page: int) -> None:
    async with get_sessionmaker()() as session:
        window = await fetch_history_window(session, account_id=account.id, page=page)
    rows, has_next = page_slice(window, PAGE_SIZE)
    if not rows and page == 0:
        await target.answer(await i18n("history.empty"))
        return
    entries = [(bp.id, await render_history_label(i18n, bp)) for bp in rows]
    await target.answer(
        await i18n("history.title"),
        reply_markup=await history_list_kb(entries, page, has_next, i18n),
    )


async def show_history(message, account: Account, i18n: Translator, page: int = 0) -> None:
    await _render_list(message, account, i18n, page)


@router.callback_query(HistoryCb.filter(F.action == "page"))
async def on_page(
    query: CallbackQuery, callback_data: HistoryCb, account: Account, i18n: Translator
) -> None:
    await _render_list(query.message, account, i18n, callback_data.page)
    await query.answer()


@router.callback_query(HistoryCb.filter(F.action == "open"))
async def on_open(
    query: CallbackQuery, callback_data: HistoryCb, account: Account, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        bp = await session.get(Blueprint, callback_data.bp_id)
    if bp is None or bp.account_id != account.id:
        await query.answer(await i18n("history.not_found"), show_alert=True)
        return
    await query.message.answer(
        await render_detail(i18n, bp),
        reply_markup=await blueprint_detail_kb(bp.id, can_download=bool(bp.llm_md), i18n=i18n),
    )
    await query.answer()


@router.callback_query(BlueprintCb.filter(F.action == "download"))
async def on_download(
    query: CallbackQuery, callback_data: BlueprintCb, account: Account, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        bp = await session.get(Blueprint, callback_data.bp_id)
    if bp is None or bp.account_id != account.id or not bp.llm_md:
        await query.answer(await i18n("history.unavailable"), show_alert=True)
        return
    await query.message.answer_document(
        BufferedInputFile(bp.llm_md.encode(), filename=f"blueprint-{bp.id}.md")
    )
    await query.answer()


@router.callback_query(BlueprintCb.filter(F.action == "preview"))
async def on_preview(
    query: CallbackQuery, callback_data: BlueprintCb, account: Account, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        bp = await session.get(Blueprint, callback_data.bp_id)
    if bp is None or bp.account_id != account.id or not bp.llm_md:
        await query.answer(await i18n("history.unavailable"), show_alert=True)
        return
    await query.message.answer(bp.llm_md[:500])
    await query.answer()


@router.callback_query(BlueprintCb.filter(F.action == "back"))
async def on_back(query: CallbackQuery, account: Account, i18n: Translator) -> None:
    await _render_list(query.message, account, i18n, 0)
    await query.answer()
