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
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)


router = Router(name="channel_discovery_router")


## FSM для поиска каналов
class ChannelDiscoveryStates(StatesGroup):
    """Состояния для работы с автопоиском каналов"""
    waiting_for_keywords = State()  # Ожидание ключевых слов от пользователя


## Меню автопоиска каналов
@router.callback_query(F.data == "channels:discovery", OperatorFilter())
async def show_channel_discovery_menu(callback: CallbackQuery):
    """
    ## Показать меню автопоиска каналов
    """
    async with get_session() as session:
        # Получаем статистику по кандидатам
        stats = await crud.get_candidates_statistics(session)
    
    menu_text = (
        "🔍 <b>Автопоиск каналов</b>\n\n"
        "Система автоматически находит релевантные Telegram-каналы "
        "для мониторинга лидов и оценивает их с помощью AI.\n\n"
        "📊 <b>Статистика кандидатов:</b>\n"
        f"• Всего найдено: {stats['total']}\n"
        f"• Ожидают проверки: {stats['pending']}\n"
        f"• Добавлено в мониторинг: {stats['added']}\n"
        f"• Отклонено: {stats['rejected']}\n\n"
        "Выберите действие:"
    )
    
    await callback.message.edit_text(
        menu_text,
        reply_markup=get_channel_discovery_menu_keyboard()
    )
    await callback.answer()


## Запуск автопоиска
@router.callback_query(F.data == "channels:start_search", OperatorFilter())
async def start_channel_search(callback: CallbackQuery, state: FSMContext):
    """
    ## Запустить автопоиск каналов
    """
    # Показываем сообщение о процессе
    search_text = (
        "🚀 <b>Запуск автопоиска каналов...</b>\n\n"
        f"Буду искать каналы по ключевым словам:\n"
        f"<code>{', '.join(settings.channel_search_keywords_list[:10])}</code>\n"
        f"{f'и ещё {len(settings.channel_search_keywords_list) - 10}...' if len(settings.channel_search_keywords_list) > 10 else ''}\n\n"
        "⏳ Это может занять несколько минут...\n"
        "Я найду каналы, соберу посты и проведу AI-оценку."
    )
    
    await callback.message.edit_text(search_text)
    await callback.answer()
    
    try:
        # Импортируем необходимые модули для работы с Telethon
        # Для простоты используем Lead Listener API
        import httpx
        
        # Отправляем запрос на поиск каналов через Lead Listener
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{settings.admin_bot_api_url.replace('admin_bot', 'lead_listener').replace('8000', '8001')}/api/discover_channels",
                    json={
                        "limit_per_query": 3,  ## Уменьшили до 3 каналов на запрос для быстрого результата
                        "evaluate_with_ai": True
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    candidate_ids = result.get("candidate_ids", [])
                    
                    # Получаем статистику
                    async with get_session() as session:
                        stats = await crud.get_candidates_statistics(session)
                    
                    success_text = (
                        "✅ <b>Автопоиск завершён!</b>\n\n"
                        f"🎯 Найдено новых каналов: {len(candidate_ids)}\n\n"
                        "📊 <b>Общая статистика:</b>\n"
                        f"• Всего кандидатов: {stats['total']}\n"
                        f"• Ожидают проверки: {stats['pending']}\n"
                        f"• Добавлено в мониторинг: {stats['added']}\n\n"
                        "Используйте кнопку ниже, чтобы посмотреть рекомендации."
                    )
                    
                    await callback.message.edit_text(
                        success_text,
                        reply_markup=get_channel_discovery_menu_keyboard()
                    )
                else:
                    raise Exception(f"Ошибка API: {response.status_code}")
            
            except httpx.TimeoutException:
                error_text = (
                    "⏱ <b>Превышено время ожидания</b>\n\n"
                    "Поиск каналов занял слишком много времени.\n"
                    "Попробуйте снова или уменьшите количество ключевых слов."
                )
                await callback.message.edit_text(
                    error_text,
                    reply_markup=get_channel_discovery_menu_keyboard()
                )
    
    except Exception as e:
        logger.error(f"Ошибка автопоиска каналов: {e}", exc_info=True)
        error_text = (
            f"❌ <b>Ошибка при поиске каналов</b>\n\n"
            f"Произошла ошибка: {str(e)}\n\n"
            "Попробуйте снова позже или обратитесь к администратору."
        )
        await callback.message.edit_text(
            error_text,
            reply_markup=get_channel_discovery_menu_keyboard()
        )


## Просмотр рекомендованных каналов
@router.callback_query(F.data == "channels:view_recommendations", OperatorFilter())
async def view_channel_recommendations(callback: CallbackQuery, state: FSMContext):
    """
    ## Показать список рекомендованных каналов
    """
    async with get_session() as session:
        # Получаем топ-кандидатов с AI-оценкой
        top_candidates = await crud.get_pending_candidates(
            session=session,
            min_score=settings.channel_min_score_threshold,
            limit=50
        )
    
    if not top_candidates:
        no_candidates_text = (
            "🤷 <b>Нет рекомендованных каналов</b>\n\n"
            "Запустите автопоиск, чтобы найти новые каналы."
        )
        await callback.message.edit_text(
            no_candidates_text,
            reply_markup=get_channel_discovery_menu_keyboard()
        )
        await callback.answer()
        return
    
    # Сортируем по score
    top_candidates = sorted(
        [c for c in top_candidates if c.ai_score is not None],
        key=lambda c: c.ai_score,
        reverse=True
    )
    
    # Показываем первого кандидата
    await state.update_data(
        candidates=[c.id for c in top_candidates],
        current_index=0
    )
    
    await show_candidate_card(callback.message, top_candidates[0], 0, len(top_candidates), state)
    await callback.answer()


## Показать карточку кандидата
async def show_candidate_card(
    message: Message,
    candidate,
    index: int,
    total: int,
    state: FSMContext
):
    """
    ## Отобразить карточку кандидата канала
    """
    # Эмодзи для score
    if candidate.ai_score >= 8:
        score_emoji = "🔥"
    elif candidate.ai_score >= 6:
        score_emoji = "✅"
    elif candidate.ai_score >= 4:
        score_emoji = "⚠️"
    else:
        score_emoji = "❌"
    
    card_text = (
        f"📺 <b>Канал {index + 1} из {total}</b>\n\n"
        f"<b>{candidate.title}</b>\n"
        f"{'@' + candidate.username if candidate.username else '(нет username)'}\n\n"
    )
    
    # Описание
    if candidate.description:
        desc_preview = candidate.description[:200]
        if len(candidate.description) > 200:
            desc_preview += "..."
        card_text += f"📝 {desc_preview}\n\n"
    
    # Метрики
    card_text += "📊 <b>Метрики:</b>\n"
    if candidate.members_count:
        card_text += f"• Подписчиков: {candidate.members_count:,}\n"
    card_text += f"• Источник: {candidate.source}\n\n"
    
    # AI-оценка
    if candidate.ai_score is not None:
        card_text += (
            f"🤖 <b>AI-оценка:</b> {score_emoji} {candidate.ai_score:.1f}/10\n"
            f"📁 <b>Тип контента:</b> {candidate.ai_order_type or 'не определён'}\n\n"
        )
        
        if candidate.ai_comment:
            card_text += f"💬 <b>Комментарий AI:</b>\n{candidate.ai_comment}\n\n"
    
    # Ссылка
    if candidate.invite_link:
        card_text += f"🔗 <a href='{candidate.invite_link}'>Открыть канал</a>"
    
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
async def navigate_candidates(callback: CallbackQuery, state: FSMContext):
    """
    ## Навигация между кандидатами
    """
    direction = callback.data.split(":")[2]  # prev или next
    
    data = await state.get_data()
    candidates = data.get("candidates", [])
    current_index = data.get("current_index", 0)
    
    if not candidates:
        await callback.answer("❌ Список кандидатов пуст")
        return
    
    # Вычисляем новый индекс
    if direction == "next":
        new_index = (current_index + 1) % len(candidates)
    else:  # prev
        new_index = (current_index - 1) % len(candidates)
    
    await state.update_data(current_index=new_index)
    
    # Получаем кандидата из БД
    async with get_session() as session:
        candidate = await crud.get_channel_candidate_by_id(
            session,
            candidates[new_index]
        )
    
    if candidate:
        await show_candidate_card(callback.message, candidate, new_index, len(candidates), state)
    
    await callback.answer()


## Добавить канал в whitelist
@router.callback_query(F.data.startswith("candidate:add:"), OperatorFilter())
async def add_candidate_to_whitelist(callback: CallbackQuery, state: FSMContext):
    """
    ## Добавить кандидата в whitelist для мониторинга
    """
    candidate_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        candidate = await crud.get_channel_candidate_by_id(session, candidate_id)
        
        if not candidate:
            await callback.answer("❌ Кандидат не найден")
            return
        
        # Проверяем, существует ли уже такой чат
        existing_chat = None
        if candidate.username:
            # Ищем по username (без @)
            username_clean = candidate.username.lstrip('@')
            all_chats = await crud.get_all_chats(session, enabled_only=False)
            existing_chat = next(
                (c for c in all_chats if c.username and c.username.lower() == username_clean.lower()),
                None
            )
        
        if existing_chat:
            await callback.answer("ℹ️ Этот канал уже есть в списке", show_alert=True)
            return
        
        # Создаём новый чат
        try:
            new_chat = await crud.create_chat(
                session=session,
                tg_chat_id=candidate.tg_chat_id or 0,  # Будет обновлено при первом мониторинге
                title=candidate.title,
                username=candidate.username.lstrip('@') if candidate.username else None,
                chat_type="channel",
                is_whitelisted=True,
                enabled=True,
                priority=10 if candidate.ai_score and candidate.ai_score >= 8 else 5
            )
            
            # Помечаем кандидата как добавленного
            await crud.mark_candidate_as_added(session, candidate_id)
            await session.commit()
            
            await callback.answer(
                f"✅ Канал '{candidate.title}' добавлен в мониторинг!",
                show_alert=True
            )
            
            # Переходим к следующему кандидату
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
                        state
                    )
            else:
                # Все кандидаты просмотрены
                await callback.message.edit_text(
                    "🎉 <b>Все рекомендованные каналы просмотрены!</b>\n\n"
                    "Запустите новый поиск или вернитесь в меню.",
                    reply_markup=get_channel_discovery_menu_keyboard()
                )
        
        except Exception as e:
            logger.error(f"Ошибка добавления канала: {e}", exc_info=True)
            await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


## Игнорировать кандидата
@router.callback_query(F.data.startswith("candidate:ignore:"), OperatorFilter())
async def ignore_candidate(callback: CallbackQuery, state: FSMContext):
    """
    ## Отклонить кандидата
    """
    candidate_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        # Помечаем как отклонённого
        await crud.mark_candidate_as_rejected(session, candidate_id)
        await session.commit()
    
    await callback.answer("🚫 Канал отклонён")
    
    # Переходим к следующему
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
                    state
                )
    else:
        await callback.message.edit_text(
            "🎉 <b>Все рекомендованные каналы просмотрены!</b>",
            reply_markup=get_channel_discovery_menu_keyboard()
        )


## Массовое добавление лучших каналов
@router.callback_query(F.data == "channels:add_top", OperatorFilter())
async def add_top_channels(callback: CallbackQuery):
    """
    ## Массовое добавление топ-каналов в whitelist
    """
    await callback.message.edit_text(
        "⏳ Добавляю лучшие каналы в мониторинг..."
    )
    
    async with get_session() as session:
        # Получаем топ-кандидатов (score >= 7.0)
        top_candidates = await crud.get_pending_candidates(
            session=session,
            min_score=7.0,
            limit=20
        )
        
        added_count = 0
        skipped_count = 0
        
        for candidate in top_candidates:
            # Проверяем, есть ли уже
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
                # Добавляем
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
    
    result_text = (
        "✅ <b>Массовое добавление завершено!</b>\n\n"
        f"• Добавлено каналов: {added_count}\n"
        f"• Пропущено (уже есть): {skipped_count}\n\n"
        "Теперь эти каналы будут мониториться автоматически."
    )
    
    await callback.message.edit_text(
        result_text,
        reply_markup=get_channel_discovery_menu_keyboard()
    )
    await callback.answer()


## Назад к меню
@router.callback_query(F.data == "channels:back", OperatorFilter())
async def back_to_chats_menu(callback: CallbackQuery):
    """
    ## Вернуться в меню чатов
    """
    from admin_bot.keyboards import get_chats_menu_keyboard
    
    await callback.message.edit_text(
        "💬 <b>Управление чатами</b>\n\n"
        "Выберите действие:",
        reply_markup=get_chats_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

