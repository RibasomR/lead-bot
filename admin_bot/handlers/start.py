"""
## Хендлеры базовых команд
Обработка команд /start, /help и главного меню.
"""

import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import get_main_menu_keyboard
from config import settings
from shared.database.engine import get_session
from shared.database.crud import get_leads_statistics

logger = logging.getLogger(__name__)


router = Router(name="start_router")


## Текст главного меню (используется в /start, /menu и callback menu:main)
MAIN_MENU_TEXT = (
    "👋 <b>Добро пожаловать в LeadHunter!</b>\n\n"
    "Я помогу вам находить и обрабатывать лиды из Telegram-чатов.\n\n"
    "🎯 <b>Что я умею:</b>\n"
    "• Мониторю выбранные чаты на наличие заказов\n"
    "• Анализирую лиды с помощью ИИ\n"
    "• Предлагаю варианты ответов и цены\n"
    "• Отправляю сообщения от ваших аккаунтов\n\n"
    "📚 Используйте /help для подробной справки.\n"
    "🎛 Выберите раздел в меню ниже:"
)


## Команда /start
@router.message(CommandStart(), OperatorFilter())
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение и главное меню.
    """
    await message.answer(
        MAIN_MENU_TEXT,
        reply_markup=get_main_menu_keyboard()
    )


## Команда /help
@router.message(Command("help"), OperatorFilter())
async def cmd_help(message: Message):
    """
    Обработчик команды /help.
    Отправляет подробную справку по использованию бота.
    """
    help_text = (
        "📖 <b>Справка по LeadHunter</b>\n\n"
        
        "🎯 <b>Основные разделы:</b>\n\n"
        
        "<b>📊 Статистика</b>\n"
        "Общая информация о лидах, чатах и аккаунтах.\n\n"
        
        "<b>📬 Лиды</b>\n"
        "Просмотр найденных лидов:\n"
        "• 🆕 Новые — ещё не просмотрены\n"
        "• 👁 Просмотренные — уже открывали\n"
        "• ✅ Отвеченные — уже отправили ответ\n"
        "• 🚫 Игнорированные — отклонены\n\n"
        
        "<b>💬 Чаты</b>\n"
        "Управление чатами для мониторинга:\n"
        "• Добавление новых чатов\n"
        "• Включение/выключение мониторинга\n"
        "• Белый и чёрный списки\n\n"
        
        "<b>👤 Аккаунты</b>\n"
        "Управление Telegram-аккаунтами:\n"
        "• Добавление новых аккаунтов\n"
        "• Настройка стилей общения\n"
        "• Активация/деактивация\n\n"
        
        "<b>⚙️ Настройки</b>\n"
        "Настройка параметров системы:\n"
        "• Ключевые слова для поиска\n"
        "• Лимиты отправки сообщений\n"
        "• Параметры ИИ\n\n"
        
        "💡 <b>Стили общения:</b>\n"
        "🎩 <b>Вежливый/Деловой</b> — официальный тон\n"
        "😊 <b>Дружеский</b> — неформальное общение\n"
        "💪 <b>Агрессивный</b> — напористый стиль\n\n"
        
        "🤖 <b>Работа с лидами:</b>\n"
        "1. Получаете уведомление о новом лиде\n"
        "2. Просматриваете карточку с анализом ИИ\n"
        "3. Выбираете аккаунт и стиль ответа\n"
        "4. Редактируете текст при необходимости\n"
        "5. Отправляете сообщение одной кнопкой\n\n"
        
        "❓ <b>Команды:</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/menu — открыть меню\n"
        "/stats — быстрая статистика\n\n"
        
        "🔐 Доступ к боту имеете только вы.\n"
        "📝 Все действия логируются для безопасности."
    )
    
    await message.answer(help_text)


## Команда /menu
@router.message(Command("menu"), OperatorFilter())
async def cmd_menu(message: Message):
    """
    Обработчик команды /menu.
    Отправляет главное меню.
    """
    await message.answer(
        MAIN_MENU_TEXT,
        reply_markup=get_main_menu_keyboard()
    )


## Команда /stats
@router.message(Command("stats"), OperatorFilter())
async def cmd_stats(message: Message):
    """
    Обработчик команды /stats.
    Отправляет краткую статистику.
    """
    async with get_session() as session:
        stats = await get_leads_statistics(session)
    
    stats_text = (
        "📊 <b>Статистика LeadHunter</b>\n\n"
        f"📬 <b>Всего лидов:</b> {stats['total']}\n"
        f"🆕 <b>Новые:</b> {stats['new']}\n"
        f"👁 <b>Просмотренные:</b> {stats['viewed']}\n"
        f"✅ <b>Отвеченные:</b> {stats['replied']}\n"
        f"🚫 <b>Игнорированные:</b> {stats['ignored']}\n\n"
        "Используйте меню для подробной информации."
    )
    
    await message.answer(
        stats_text,
        reply_markup=get_main_menu_keyboard()
    )


## Callback главного меню
@router.callback_query(F.data == "menu:main", OperatorFilter())
async def callback_main_menu(callback: CallbackQuery):
    """
    Обработчик callback главного меню.
    """
    await callback.message.edit_text(
        MAIN_MENU_TEXT,
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


## Callback статистики
@router.callback_query(F.data == "menu:stats", OperatorFilter())
async def callback_stats_menu(callback: CallbackQuery):
    """
    Обработчик callback меню статистики.
    """
    async with get_session() as session:
        stats = await get_leads_statistics(session)
    
    stats_text = (
        "📊 <b>Статистика LeadHunter</b>\n\n"
        f"📬 <b>Всего лидов:</b> {stats['total']}\n"
        f"🆕 <b>Новые:</b> {stats['new']}\n"
        f"👁 <b>Просмотренные:</b> {stats['viewed']}\n"
        f"✅ <b>Отвеченные:</b> {stats['replied']}\n"
        f"🚫 <b>Игнорированные:</b> {stats['ignored']}\n\n"
        "Используйте меню для подробной информации."
    )
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


## Callback настроек
@router.callback_query(F.data == "menu:settings", OperatorFilter())
async def callback_settings_menu(callback: CallbackQuery):
    """
    Обработчик callback меню настроек.
    """
    settings_text = (
        "⚙️ <b>Настройки LeadHunter</b>\n\n"
        "<b>Текущие настройки:</b>\n\n"
        f"🤖 <b>Модель AI (primary):</b> {settings.ai_model_primary}\n"
        f"🤖 <b>Модель AI (secondary):</b> {settings.ai_model_secondary}\n"
        f"⏱ <b>Таймаут AI:</b> {settings.ai_request_timeout}с\n\n"
        f"📊 <b>Макс. ответов в час:</b> {settings.max_replies_per_chat_per_hour}\n"
        f"⏳ <b>Задержка между отправками:</b> {settings.min_send_delay}-{settings.max_send_delay}с\n\n"
        "💡 <i>Для изменения настроек отредактируйте .env и перезапустите контейнеры</i>"
    )
    
    await callback.message.edit_text(
        settings_text,
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


## Callback профиля фрилансера (v2) — делегируем в profile.py
@router.callback_query(F.data == "menu:profile", OperatorFilter())
async def callback_profile_menu(callback: CallbackQuery):
    """
    Перенаправляет в меню профиля. Обработка в handlers/profile.py.
    """
    from admin_bot.handlers.profile import show_profile
    await show_profile(callback)


## Callback поиска (v2) — делегируем в search.py
@router.callback_query(F.data == "menu:search", OperatorFilter())
async def callback_search_menu(callback: CallbackQuery):
    """
    Перенаправляет в меню поиска. Обработка в handlers/search.py.
    """
    from admin_bot.handlers.search import callback_search_main
    await callback_search_main(callback)


## Обработка неизвестных команд от оператора
@router.message(OperatorFilter())
async def unknown_command(message: Message):
    """
    Обработчик неизвестных команд.
    """
    await message.answer(
        "❓ Неизвестная команда.\n\n"
        "Используйте /help для справки или /menu для открытия меню.",
        reply_markup=get_main_menu_keyboard()
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

