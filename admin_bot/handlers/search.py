"""
## Хендлеры глобального поиска (v2)
Управление поисковыми фразами, запуск поиска, статистика.
"""

import logging
from datetime import timezone, timedelta

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.markdown import hbold, hitalic, hcode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import get_main_menu_keyboard
from shared.database.engine import get_session
from shared.database.crud import (
    get_all_search_queries,
    create_search_query,
    update_search_query_status,
    delete_search_query,
    count_search_queries_today,
)
from config import settings

logger = logging.getLogger(__name__)

router = Router(name="search_router")


## FSM для добавления поискового запроса
class AddSearchQueryStates(StatesGroup):
    waiting_for_query_text = State()


## Клавиатура меню поиска
def get_search_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Мои фразы", callback_data="search:list")
    builder.button(text="➕ Добавить фразу", callback_data="search:add")
    builder.button(text="🚀 Запустить поиск", callback_data="search:run")
    builder.button(text="🔙 В меню", callback_data="menu:main")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


## Показ меню поиска
@router.callback_query(F.data == "search:menu", OperatorFilter())
async def callback_search_main(callback: CallbackQuery):
    """
    Главное меню глобального поиска.
    """
    async with get_session() as session:
        queries = await get_all_search_queries(session)
        today_count = await count_search_queries_today(session)

    text = (
        f"🔍 {hbold('Глобальный поиск (Premium)')}\n\n"
        f"📋 Фраз: {len(queries)}\n"
        f"📊 Поисков сегодня: {today_count}/10\n\n"
        f"{hitalic('Поиск использует Telegram search_global (Premium).')}"
    )
    await callback.message.edit_text(text, reply_markup=get_search_menu_keyboard())
    await callback.answer()


## Список фраз
@router.callback_query(F.data == "search:list", OperatorFilter())
async def callback_search_list(callback: CallbackQuery):
    """
    Список поисковых фраз.
    """
    async with get_session() as session:
        queries = await get_all_search_queries(session)

    if not queries:
        await callback.message.edit_text(
            f"📋 {hbold('Поисковые фразы')}\n\n"
            f"{hitalic('Пока нет фраз. Добавьте первую!')}",
            reply_markup=get_search_menu_keyboard()
        )
        await callback.answer()
        return

    lines = [f"📋 {hbold('Поисковые фразы')}", ""]
    for q in queries:
        status = "✅" if q.enabled else "⛔"
        used = q.last_used_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime("%d.%m %H:%M") if q.last_used_at else "никогда"
        lines.append(f"{status} #{q.id} {hcode(q.query_text)}")
        lines.append(f"   📊 {q.results_count or 0} результатов | 🕐 {used}")

    text = "\n".join(lines)

    ## Кнопки для каждой фразы
    builder = InlineKeyboardBuilder()
    for q in queries:
        toggle_text = "⛔" if q.enabled else "✅"
        builder.button(text=f"{toggle_text} #{q.id}", callback_data=f"search:toggle:{q.id}")
        builder.button(text=f"🗑 #{q.id}", callback_data=f"search:delete:{q.id}")

    builder.button(text="➕ Добавить", callback_data="search:add")
    builder.button(text="🔙 Назад", callback_data="search:menu")

    ## Раскладка: пары toggle+delete, затем add и back
    rows = [2] * len(queries) + [1, 1]
    builder.adjust(*rows)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


## Добавление фразы — начало
@router.callback_query(F.data == "search:add", OperatorFilter())
async def callback_search_add(callback: CallbackQuery, state: FSMContext):
    """
    Начинает процесс добавления поисковой фразы.
    """
    await state.set_state(AddSearchQueryStates.waiting_for_query_text)
    await callback.message.edit_text(
        f"➕ {hbold('Добавление поисковой фразы')}\n\n"
        f"Введите фразу для поиска:\n\n"
        f"Примеры:\n"
        f"• {hcode('нужен бот telegram')}\n"
        f"• {hcode('ищу разработчика python')}\n"
        f"• {hcode('автоматизация n8n')}\n\n"
        f"Отправьте /cancel для отмены."
    )
    await callback.answer()


## Добавление фразы — ввод текста
@router.message(AddSearchQueryStates.waiting_for_query_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_search_query_text(message: Message, state: FSMContext):
    """
    Сохраняет поисковую фразу.
    """
    query_text = message.text.strip()
    if len(query_text) < 3:
        await message.answer("❌ Фраза слишком короткая. Минимум 3 символа.")
        return

    async with get_session() as session:
        query = await create_search_query(session, query_text=query_text)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Фраза добавлена: {hcode(query_text)}\n"
        f"ID: #{query.id}",
        reply_markup=get_search_menu_keyboard()
    )


## Переключение статуса фразы
@router.callback_query(F.data.startswith("search:toggle:"), OperatorFilter())
async def callback_search_toggle(callback: CallbackQuery):
    """
    Включает/выключает поисковую фразу.
    """
    query_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        from shared.database.crud import get_search_query_by_id
        query = await get_search_query_by_id(session, query_id)
        if query:
            new_status = not query.enabled
            await update_search_query_status(session, query_id, new_status)
            await session.commit()
            status_text = "включена" if new_status else "выключена"
            await callback.answer(f"{'✅' if new_status else '⛔'} Фраза {status_text}")
        else:
            await callback.answer("❌ Фраза не найдена", show_alert=True)
            return

    ## Обновляем список
    await callback_search_list(callback)


## Удаление фразы
@router.callback_query(F.data.startswith("search:delete:"), OperatorFilter())
async def callback_search_delete(callback: CallbackQuery):
    """
    Удаляет поисковую фразу.
    """
    query_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await delete_search_query(session, query_id)
        await session.commit()

    if success:
        await callback.answer("🗑 Фраза удалена")
    else:
        await callback.answer("❌ Фраза не найдена", show_alert=True)
        return

    await callback_search_list(callback)


## Запуск поиска
@router.callback_query(F.data == "search:run", OperatorFilter())
async def callback_search_run(callback: CallbackQuery):
    """
    Запускает глобальный поиск через Lead Listener API.
    """
    await callback.answer("⏳ Запуск поиска...")

    try:
        ## Вызываем API Lead Listener
        lead_listener_url = settings.admin_bot_api_url.replace("admin_bot", "lead_listener").replace("8000", "8001")
        api_url = f"{lead_listener_url}/api/search_global"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, json={})

        if response.status_code == 200:
            data = response.json()
            stats = data.get("stats", {})

            await callback.message.edit_text(
                f"✅ {hbold('Поиск завершён')}\n\n"
                f"🔍 Запросов: {stats.get('queries_executed', 0)}\n"
                f"📊 Найдено: {stats.get('total_found', 0)}\n"
                f"🎯 Лидов: {stats.get('total_leads', 0)}\n\n"
                + (
                    f"⚠️ Ошибки: {', '.join(stats.get('errors', []))}"
                    if stats.get("errors")
                    else ""
                ),
                reply_markup=get_search_menu_keyboard()
            )
        else:
            error = response.json().get("error", "Unknown error")
            await callback.message.edit_text(
                f"❌ {hbold('Ошибка поиска')}\n\n{error}",
                reply_markup=get_search_menu_keyboard()
            )

    except httpx.TimeoutException:
        await callback.message.edit_text(
            f"⏳ {hbold('Поиск запущен')}\n\n"
            f"Результаты появятся в лидах.",
            reply_markup=get_search_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка запуска поиска: {e}")
        await callback.message.edit_text(
            f"❌ {hbold('Ошибка')}\n\n{str(e)[:200]}",
            reply_markup=get_search_menu_keyboard()
        )


## Отмена
@router.message(F.text == "/cancel", AddSearchQueryStates())
async def cancel_search_add(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Добавление отменено.",
        reply_markup=get_search_menu_keyboard()
    )
