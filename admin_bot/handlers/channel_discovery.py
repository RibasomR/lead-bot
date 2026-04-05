"""
## [DEPRECATED v2] Хендлеры для автопоиска каналов (Фаза 7.3)
Заменяется глобальным поиском search_global (handlers/search.py).
Файл оставлен для обратной совместимости.
"""

import logging
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import (
    get_channel_discovery_menu_keyboard,
    get_channel_candidate_keyboard,
    get_candidates_list_keyboard
)
from config import settings
from shared.database.engine import get_session
from shared.database import crud
from shared.database.models import ChannelSource
from shared.channel_discovery import ChannelDiscoveryService, TelegramSearchProvider
from shared.locales import t
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)


router = Router(name="channel_discovery_router")


## FSM для поиска каналов
class ChannelDiscoveryStates(StatesGroup):
    """Состояния для работы с автопоиском каналов"""
    waiting_for_keywords = State()  # Ожидание ключевых слов от пользователя


## Меню автопоиска каналов
@router.callback_query(F.data == "channels:discovery", OperatorFilter())
async def show_channel_discovery_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    ## Показать меню автопоиска каналов
    """
    async with get_session() as session:
        # Получаем статистику по кандидатам
        stats = await crud.get_candidates_statistics(session)

    menu_text = (
        t("discovery.menu_title", lang)
        + t("discovery.stats_title", lang)
        + t("discovery.stats_total", lang, count=stats['total'])
        + t("discovery.stats_pending", lang, count=stats['pending'])
        + t("discovery.stats_added", lang, count=stats['added'])
        + t("discovery.stats_rejected", lang, count=stats['rejected'])
        + t("discovery.action_prompt", lang)
    )

    await callback.message.edit_text(
        menu_text,
        reply_markup=get_channel_discovery_menu_keyboard(lang)
    )
    await callback.answer()


## Запуск автопоиска
@router.callback_query(F.data == "channels:start_search", OperatorFilter())
async def start_channel_search(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Запустить автопоиск каналов
    """
    keywords = settings.channel_search_keywords_list[:10]
    more_count = len(settings.channel_search_keywords_list) - 10

    search_text = (
        t("discovery.search_started", lang)
        + t("discovery.search_keywords", lang)
        + f"<code>{', '.join(keywords)}</code>\n"
        + (t("discovery.search_more", lang, count=more_count) if more_count > 0 else "")
        + t("discovery.search_wait", lang)
    )

    await callback.message.edit_text(search_text)
    await callback.answer()

    try:
        import httpx

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{settings.admin_bot_api_url.replace('admin_bot', 'lead_listener').replace('8000', '8001')}/api/discover_channels",
                    json={
                        "limit_per_query": 3,
                        "evaluate_with_ai": True
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    candidate_ids = result.get("candidate_ids", [])

                    async with get_session() as session:
                        stats = await crud.get_candidates_statistics(session)

                    success_text = (
                        t("discovery.search_done", lang, count=len(candidate_ids))
                        + t("discovery.search_overall", lang)
                        + t("discovery.stats_total", lang, count=stats['total'])
                        + t("discovery.stats_pending", lang, count=stats['pending'])
                        + t("discovery.stats_added", lang, count=stats['added'])
                        + t("discovery.search_view_prompt", lang)
                    )

                    await callback.message.edit_text(
                        success_text,
                        reply_markup=get_channel_discovery_menu_keyboard(lang)
                    )
                else:
                    raise Exception(f"API error: {response.status_code}")

            except httpx.TimeoutException:
                await callback.message.edit_text(
                    t("discovery.search_timeout", lang),
                    reply_markup=get_channel_discovery_menu_keyboard(lang)
                )

    except Exception as e:
        logger.error(f"Ошибка автопоиска каналов: {e}", exc_info=True)
        await callback.message.edit_text(
            t("discovery.search_error", lang, error=str(e)),
            reply_markup=get_channel_discovery_menu_keyboard(lang)
        )


## Просмотр рекомендованных каналов
@router.callback_query(F.data == "channels:view_recommendations", OperatorFilter())
async def view_channel_recommendations(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Показать список рекомендованных каналов
    """
    async with get_session() as session:
        top_candidates = await crud.get_pending_candidates(
            session=session,
            min_score=settings.channel_min_score_threshold,
            limit=50
        )

    if not top_candidates:
        await callback.message.edit_text(
            t("discovery.no_recommendations", lang),
            reply_markup=get_channel_discovery_menu_keyboard(lang)
        )
        await callback.answer()
        return

    top_candidates = sorted(
        [c for c in top_candidates if c.ai_score is not None],
        key=lambda c: c.ai_score,
        reverse=True
    )

    await state.update_data(
        candidates=[c.id for c in top_candidates],
        current_index=0
    )

    await show_candidate_card(callback.message, top_candidates[0], 0, len(top_candidates), state, lang)
    await callback.answer()


## Показать карточку кандидата
async def show_candidate_card(
    message: Message,
    candidate,
    index: int,
    total: int,
    state: FSMContext,
    lang: str = "ru"
):
    """
    ## Отобразить карточку кандидата канала
    """
    if candidate.ai_score >= 8:
        score_emoji = "🔥"
    elif candidate.ai_score >= 6:
        score_emoji = "✅"
    elif candidate.ai_score >= 4:
        score_emoji = "⚠️"
    else:
        score_emoji = "❌"

    card_text = t("discovery.candidate_card", lang, index=index + 1, total=total)
    card_text += f"<b>{candidate.title}</b>\n"
    card_text += f"{'@' + candidate.username if candidate.username else t('discovery.no_username', lang)}\n\n"

    if candidate.description:
        desc_preview = candidate.description[:200]
        if len(candidate.description) > 200:
            desc_preview += "..."
        card_text += f"📝 {desc_preview}\n\n"

    card_text += t("discovery.metrics_title", lang)
    if candidate.members_count:
        card_text += t("discovery.members", lang, count=f"{candidate.members_count:,}")
    card_text += t("discovery.source", lang, source=candidate.source) + "\n"

    if candidate.ai_score is not None:
        card_text += t("discovery.ai_score", lang, emoji=score_emoji, score=f"{candidate.ai_score:.1f}")
        card_text += t("discovery.ai_content_type", lang, type=candidate.ai_order_type or "?")

        if candidate.ai_comment:
            card_text += t("discovery.ai_comment", lang, comment=candidate.ai_comment)

    if candidate.invite_link:
        card_text += f"🔗 <a href='{candidate.invite_link}'>{t('discovery.open_link', lang)}</a>"

    await message.edit_text(
        card_text,
        reply_markup=get_channel_candidate_keyboard(
            candidate.id,
            index,
            total,
            candidate.ai_score or 0
        ),
        disable_web_page_preview=True
    )


## Навигация по кандидатам
@router.callback_query(F.data.startswith("candidate:nav:"), OperatorFilter())
async def navigate_candidates(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Навигация между кандидатами
    """
    direction = callback.data.split(":")[2]

    data = await state.get_data()
    candidates = data.get("candidates", [])
    current_index = data.get("current_index", 0)

    if not candidates:
        await callback.answer(t("discovery.candidates_empty", lang))
        return

    if direction == "next":
        new_index = (current_index + 1) % len(candidates)
    else:
        new_index = (current_index - 1) % len(candidates)

    await state.update_data(current_index=new_index)

    async with get_session() as session:
        candidate = await crud.get_channel_candidate_by_id(
            session,
            candidates[new_index]
        )

    if candidate:
        await show_candidate_card(callback.message, candidate, new_index, len(candidates), state, lang)

    await callback.answer()


## Добавить канал в whitelist
@router.callback_query(F.data.startswith("candidate:add:"), OperatorFilter())
async def add_candidate_to_whitelist(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Добавить кандидата в whitelist для мониторинга
    """
    candidate_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        candidate = await crud.get_channel_candidate_by_id(session, candidate_id)

        if not candidate:
            await callback.answer(t("discovery.candidate_not_found", lang))
            return

        existing_chat = None
        if candidate.username:
            username_clean = candidate.username.lstrip('@')
            all_chats = await crud.get_all_chats(session, enabled_only=False)
            existing_chat = next(
                (c for c in all_chats if c.username and c.username.lower() == username_clean.lower()),
                None
            )

        if existing_chat:
            await callback.answer(t("discovery.already_in_list", lang), show_alert=True)
            return

        try:
            new_chat = await crud.create_chat(
                session=session,
                tg_chat_id=candidate.tg_chat_id or 0,
                title=candidate.title,
                username=candidate.username.lstrip('@') if candidate.username else None,
                chat_type="channel",
                is_whitelisted=True,
                enabled=True,
                priority=10 if candidate.ai_score and candidate.ai_score >= 8 else 5
            )

            await crud.mark_candidate_as_added(session, candidate_id)
            await session.commit()

            await callback.answer(
                t("discovery.added_to_monitoring", lang, title=candidate.title),
                show_alert=True
            )

            data = await state.get_data()
            candidates = data.get("candidates", [])
            current_index = data.get("current_index", 0)

            if current_index + 1 < len(candidates):
                new_index = current_index + 1
                await state.update_data(current_index=new_index)

                next_candidate = await crud.get_channel_candidate_by_id(
                    session,
                    candidates[new_index]
                )
                if next_candidate:
                    await show_candidate_card(
                        callback.message,
                        next_candidate,
                        new_index,
                        len(candidates),
                        state,
                        lang
                    )
            else:
                await callback.message.edit_text(
                    t("discovery.all_reviewed", lang),
                    reply_markup=get_channel_discovery_menu_keyboard(lang)
                )

        except Exception as e:
            logger.error(f"Ошибка добавления канала: {e}", exc_info=True)
            await callback.answer(f"❌ {str(e)}", show_alert=True)


## Игнорировать кандидата
@router.callback_query(F.data.startswith("candidate:ignore:"), OperatorFilter())
async def ignore_candidate(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Отклонить кандидата
    """
    candidate_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        await crud.mark_candidate_as_rejected(session, candidate_id)
        await session.commit()

    await callback.answer(t("discovery.ignored_toast", lang))

    data = await state.get_data()
    candidates = data.get("candidates", [])
    current_index = data.get("current_index", 0)

    if current_index + 1 < len(candidates):
        new_index = current_index + 1
        await state.update_data(current_index=new_index)

        async with get_session() as session:
            next_candidate = await crud.get_channel_candidate_by_id(
                session,
                candidates[new_index]
            )
            if next_candidate:
                await show_candidate_card(
                    callback.message,
                    next_candidate,
                    new_index,
                    len(candidates),
                    state,
                    lang
                )
    else:
        await callback.message.edit_text(
            t("discovery.all_reviewed_short", lang),
            reply_markup=get_channel_discovery_menu_keyboard(lang)
        )


## Массовое добавление лучших каналов
@router.callback_query(F.data == "channels:add_top", OperatorFilter())
async def add_top_channels(callback: CallbackQuery, lang: str = "ru"):
    """
    ## Массовое добавление топ-каналов в whitelist
    """
    await callback.message.edit_text(
        t("discovery.mass_add_progress", lang)
    )

    async with get_session() as session:
        top_candidates = await crud.get_pending_candidates(
            session=session,
            min_score=7.0,
            limit=20
        )

        added_count = 0
        skipped_count = 0

        for candidate in top_candidates:
            if candidate.username:
                username_clean = candidate.username.lstrip('@')
                all_chats = await crud.get_all_chats(session, enabled_only=False)
                existing = next(
                    (c for c in all_chats if c.username and c.username.lower() == username_clean.lower()),
                    None
                )
                if existing:
                    skipped_count += 1
                    continue

            try:
                await crud.create_chat(
                    session=session,
                    tg_chat_id=candidate.tg_chat_id or 0,
                    title=candidate.title,
                    username=candidate.username.lstrip('@') if candidate.username else None,
                    chat_type="channel",
                    is_whitelisted=True,
                    enabled=True,
                    priority=10 if candidate.ai_score >= 8 else 7
                )

                await crud.mark_candidate_as_added(session, candidate.id)
                added_count += 1

            except Exception as e:
                logger.error(f"Ошибка добавления {candidate.title}: {e}")
                skipped_count += 1

        await session.commit()

    await callback.message.edit_text(
        t("discovery.mass_add_done", lang, added=added_count, skipped=skipped_count),
        reply_markup=get_channel_discovery_menu_keyboard(lang)
    )
    await callback.answer()


## Назад к меню
@router.callback_query(F.data == "channels:back", OperatorFilter())
async def back_to_chats_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    ## Вернуться в меню чатов
    """
    from admin_bot.keyboards import get_chats_menu_keyboard

    await callback.message.edit_text(
        t("discovery.back_title", lang),
        reply_markup=get_chats_menu_keyboard(lang),
        parse_mode="HTML"
    )
    await callback.answer()
