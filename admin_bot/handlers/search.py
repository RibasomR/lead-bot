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
from shared.locales import t
from config import settings

logger = logging.getLogger(__name__)

router = Router(name="search_router")


## FSM для добавления поискового запроса
class AddSearchQueryStates(StatesGroup):
    waiting_for_query_text = State()


## Клавиатура меню поиска
def get_search_menu_keyboard(lang: str = "ru"):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("search.btn_phrases", lang), callback_data="search:list")
    builder.button(text=t("search.btn_add", lang), callback_data="search:add")
    builder.button(text=t("search.btn_run", lang), callback_data="search:run")
    builder.button(text=t("search.btn_back", lang), callback_data="menu:main")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


## Показ меню поиска
@router.callback_query(F.data == "search:menu", OperatorFilter())
async def callback_search_main(callback: CallbackQuery, lang: str = "ru"):
    """
    Главное меню глобального поиска.
    """
    async with get_session() as session:
        queries = await get_all_search_queries(session)
        today_count = await count_search_queries_today(session)

    text = (
        t("search.menu_title", lang)
        + t("search.phrases_count", lang, count=len(queries)) + "\n"
        + t("search.today_count", lang, count=today_count) + "\n\n"
        + hitalic(t("search.footer", lang))
    )
    await callback.message.edit_text(text, reply_markup=get_search_menu_keyboard(lang))
    await callback.answer()


## Список фраз
@router.callback_query(F.data == "search:list", OperatorFilter())
async def callback_search_list(callback: CallbackQuery, lang: str = "ru"):
    """
    Список поисковых фраз.
    """
    async with get_session() as session:
        queries = await get_all_search_queries(session)

    if not queries:
        await callback.message.edit_text(
            t("search.phrases_title", lang) + "\n\n"
            + hitalic(t("search.phrases_empty", lang)),
            reply_markup=get_search_menu_keyboard(lang)
        )
        await callback.answer()
        return

    lines = [t("search.phrases_title", lang), ""]
    for q in queries:
        status = "✅" if q.enabled else "⛔"
        used = q.last_used_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime("%d.%m %H:%M") if q.last_used_at else t("search.phrase_used", lang)
        lines.append(f"{status} #{q.id} {hcode(q.query_text)}")
        lines.append(f"   📊 {q.results_count or 0} results | 🕐 {used}")

    text = "\n".join(lines)

    ## Кнопки для каждой фразы
    builder = InlineKeyboardBuilder()
    for q in queries:
        toggle_text = "⛔" if q.enabled else "✅"
        builder.button(text=f"{toggle_text} #{q.id}", callback_data=f"search:toggle:{q.id}")
        builder.button(text=f"🗑 #{q.id}", callback_data=f"search:delete:{q.id}")

    builder.button(text=t("search.btn_add", lang), callback_data="search:add")
    builder.button(text=t("menu.back", lang), callback_data="search:menu")

    ## Раскладка: пары toggle+delete, затем add и back
    rows = [2] * len(queries) + [1, 1]
    builder.adjust(*rows)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


## Добавление фразы -- начало
@router.callback_query(F.data == "search:add", OperatorFilter())
async def callback_search_add(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Начинает процесс добавления поисковой фразы.
    """
    await state.set_state(AddSearchQueryStates.waiting_for_query_text)
    await callback.message.edit_text(
        t("search.add_title", lang)
        + t("search.add_prompt", lang)
        + f"• {hcode('нужен бот telegram')}\n"
        + f"• {hcode('ищу разработчика python')}\n"
        + f"• {hcode('автоматизация n8n')}\n"
        + t("search.add_cancel_prompt", lang)
    )
    await callback.answer()


## Добавление фразы -- ввод текста
@router.message(AddSearchQueryStates.waiting_for_query_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_search_query_text(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Сохраняет поисковую фразу.
    """
    query_text = message.text.strip()
    if len(query_text) < 3:
        await message.answer(t("search.add_short", lang))
        return

    async with get_session() as session:
        query = await create_search_query(session, query_text=query_text)
        await session.commit()

    await state.clear()
    await message.answer(
        t("search.add_ok", lang, text=hcode(query_text), id=query.id),
        reply_markup=get_search_menu_keyboard(lang)
    )


## Переключение статуса фразы
@router.callback_query(F.data.startswith("search:toggle:"), OperatorFilter())
async def callback_search_toggle(callback: CallbackQuery, lang: str = "ru"):
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
            status_text = t("search.toggle_on", lang) if new_status else t("search.toggle_off", lang)
            await callback.answer(status_text)
        else:
            await callback.answer(t("search.not_found", lang), show_alert=True)
            return

    ## Обновляем список
    await callback_search_list(callback, lang)


## Удаление фразы
@router.callback_query(F.data.startswith("search:delete:"), OperatorFilter())
async def callback_search_delete(callback: CallbackQuery, lang: str = "ru"):
    """
    Удаляет поисковую фразу.
    """
    query_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await delete_search_query(session, query_id)
        await session.commit()

    if success:
        await callback.answer(t("search.deleted", lang))
    else:
        await callback.answer(t("search.not_found", lang), show_alert=True)
        return

    await callback_search_list(callback, lang)


## Запуск поиска
@router.callback_query(F.data == "search:run", OperatorFilter())
async def callback_search_run(callback: CallbackQuery, lang: str = "ru"):
    """
    Запускает глобальный поиск через Lead Listener API.
    """
    await callback.answer(t("search.run_starting", lang))

    try:
        ## Вызываем API Lead Listener
        lead_listener_url = settings.admin_bot_api_url.replace("admin_bot", "lead_listener").replace("8000", "8001")
        api_url = f"{lead_listener_url}/api/search_global"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, json={})

        if response.status_code == 200:
            data = response.json()
            stats = data.get("stats", {})

            result_text = (
                t("search.run_done", lang)
                + t("search.run_queries", lang, count=stats.get('queries_executed', 0)) + "\n"
                + t("search.run_found", lang, count=stats.get('total_found', 0)) + "\n"
                + t("search.run_leads", lang, count=stats.get('total_leads', 0)) + "\n\n"
            )
            if stats.get("errors"):
                result_text += t("search.run_errors", lang, errors=', '.join(stats.get('errors', [])))

            await callback.message.edit_text(
                result_text,
                reply_markup=get_search_menu_keyboard(lang)
            )
        else:
            error = response.json().get("error", "Unknown error")
            await callback.message.edit_text(
                t("search.run_error", lang, error=error),
                reply_markup=get_search_menu_keyboard(lang)
            )

    except httpx.TimeoutException:
        await callback.message.edit_text(
            t("search.run_timeout", lang),
            reply_markup=get_search_menu_keyboard(lang)
        )
    except Exception as e:
        logger.error(f"Ошибка запуска поиска: {e}")
        await callback.message.edit_text(
            t("search.run_unexpected", lang, error=str(e)[:200]),
            reply_markup=get_search_menu_keyboard(lang)
        )


## Отмена
@router.message(F.text == "/cancel", AddSearchQueryStates())
async def cancel_search_add(message: Message, state: FSMContext, lang: str = "ru"):
    await state.clear()
    await message.answer(
        t("search.add_cancelled", lang),
        reply_markup=get_search_menu_keyboard(lang)
    )
