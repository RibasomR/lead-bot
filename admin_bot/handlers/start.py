"""
## Хендлеры базовых команд
Обработка команд /start, /help и главного меню.
"""

import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import get_main_menu_keyboard, get_language_keyboard
from config import settings
from shared.database.engine import get_session
from shared.database.crud import get_leads_statistics
from shared.locales import t

logger = logging.getLogger(__name__)


router = Router(name="start_router")


## Команда /start
@router.message(CommandStart(), OperatorFilter())
async def cmd_start(message: Message, lang: str = "ru"):
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение и главное меню.
    """
    await message.answer(
        t("start.welcome", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )


## Команда /help
@router.message(Command("help"), OperatorFilter())
async def cmd_help(message: Message, lang: str = "ru"):
    """
    Обработчик команды /help.
    Отправляет подробную справку по использованию бота.
    """
    await message.answer(t("help.text", lang))


## Команда /menu
@router.message(Command("menu"), OperatorFilter())
async def cmd_menu(message: Message, lang: str = "ru"):
    """
    Обработчик команды /menu.
    Отправляет главное меню.
    """
    await message.answer(
        t("start.welcome", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )


## Команда /stats
@router.message(Command("stats"), OperatorFilter())
async def cmd_stats(message: Message, lang: str = "ru"):
    """
    Обработчик команды /stats.
    Отправляет краткую статистику.
    """
    async with get_session() as session:
        stats = await get_leads_statistics(session)

    stats_text = (
        t("stats.title", lang) + "\n"
        + t("stats.total", lang, count=stats['total']) + "\n"
        + t("stats.new", lang, count=stats['new']) + "\n"
        + t("stats.viewed", lang, count=stats['viewed']) + "\n"
        + t("stats.replied", lang, count=stats['replied']) + "\n"
        + t("stats.ignored", lang, count=stats['ignored']) + "\n\n"
        + t("stats.footer", lang)
    )

    await message.answer(
        stats_text,
        reply_markup=get_main_menu_keyboard(lang)
    )


## Callback главного меню
@router.callback_query(F.data == "menu:main", OperatorFilter())
async def callback_main_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик callback главного меню.
    """
    await callback.message.edit_text(
        t("start.welcome", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback.answer()


## Callback статистики
@router.callback_query(F.data == "menu:stats", OperatorFilter())
async def callback_stats_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик callback меню статистики.
    """
    async with get_session() as session:
        stats = await get_leads_statistics(session)

    stats_text = (
        t("stats.title", lang) + "\n"
        + t("stats.total", lang, count=stats['total']) + "\n"
        + t("stats.new", lang, count=stats['new']) + "\n"
        + t("stats.viewed", lang, count=stats['viewed']) + "\n"
        + t("stats.replied", lang, count=stats['replied']) + "\n"
        + t("stats.ignored", lang, count=stats['ignored']) + "\n\n"
        + t("stats.footer", lang)
    )

    await callback.message.edit_text(
        stats_text,
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback.answer()


## Callback настроек
@router.callback_query(F.data == "menu:settings", OperatorFilter())
async def callback_settings_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик callback меню настроек.
    """
    settings_text = (
        t("settings.title", lang)
        + t("settings.ai_primary", lang, model=settings.ai_model_primary)
        + t("settings.ai_secondary", lang, model=settings.ai_model_secondary)
        + t("settings.ai_timeout", lang, timeout=settings.ai_request_timeout)
        + t("settings.max_replies", lang, count=settings.max_replies_per_chat_per_hour)
        + t("settings.send_delay", lang, min=settings.min_send_delay, max=settings.max_send_delay)
        + t("settings.edit_hint", lang)
    )

    await callback.message.edit_text(
        settings_text,
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback.answer()


## Callback выбора языка
@router.callback_query(F.data == "menu:language", OperatorFilter())
async def callback_language_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает кнопки выбора языка.
    """
    await callback.message.edit_text(
        t("lang.select", lang),
        reply_markup=get_language_keyboard()
    )
    await callback.answer()


## Callback установки языка
@router.callback_query(F.data.startswith("lang:set:"), OperatorFilter())
async def callback_set_language(callback: CallbackQuery):
    """
    Устанавливает выбранный язык и обновляет в БД.
    """
    new_lang = callback.data.split(":")[2]  # "ru" или "en"

    from shared.database.crud import set_operator_language
    async with get_session() as session:
        await set_operator_language(session, callback.from_user.id, new_lang)
        await session.commit()

    await callback.message.edit_text(
        t("lang.changed", new_lang),
        reply_markup=get_main_menu_keyboard(new_lang)
    )
    await callback.answer()


## Callback профиля фрилансера (v2) — делегируем в profile.py
@router.callback_query(F.data == "menu:profile", OperatorFilter())
async def callback_profile_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Перенаправляет в меню профиля. Обработка в handlers/profile.py.
    """
    from admin_bot.handlers.profile import show_profile
    await show_profile(callback, lang)


## Callback поиска (v2) — делегируем в search.py
@router.callback_query(F.data == "menu:search", OperatorFilter())
async def callback_search_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Перенаправляет в меню поиска. Обработка в handlers/search.py.
    """
    from admin_bot.handlers.search import callback_search_main
    await callback_search_main(callback, lang)


## Обработка неизвестных команд от оператора
@router.message(OperatorFilter())
async def unknown_command(message: Message, lang: str = "ru"):
    """
    Обработчик неизвестных команд.
    """
    await message.answer(
        t("unknown_cmd", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )


## Обработка сообщений не от оператора
@router.message()
async def unauthorized_access(message: Message):
    """
    Обработчик сообщений от неавторизованных пользователей.
    Игнорирует запросы без ответа для защиты от DDoS, но логирует попытки доступа.
    """
    user_id = message.from_user.id if message.from_user else None
    username = message.from_user.username if message.from_user else "Unknown"
    command = message.text if message.text else "неизвестная команда"

    logger.warning(
        f"🚫 Попытка доступа от неавторизованного пользователя: "
        f"ID={user_id}, username=@{username}, команда={command}"
    )


## Обработка callback-запросов не от оператора
@router.callback_query()
async def unauthorized_callback(callback: CallbackQuery):
    """
    Обработчик callback-запросов от неавторизованных пользователей.
    Игнорирует запросы без ответа для защиты от DDoS, но логирует попытки доступа.
    """
    user_id = callback.from_user.id if callback.from_user else None
    username = callback.from_user.username if callback.from_user else "Unknown"
    callback_data = callback.data if callback.data else "unknown"

    logger.warning(
        f"🚫 Попытка callback от неавторизованного пользователя: "
        f"ID={user_id}, username=@{username}, data={callback_data}"
    )

    # Не отвечаем на callback, чтобы не раскрывать информацию о боте
