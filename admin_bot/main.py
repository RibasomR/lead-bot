"""
## Admin Bot — главный модуль
Инициализация и запуск Admin Bot для управления системой LeadHunter.
"""

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings, validate_config
from admin_bot.handlers import setup_handlers
from admin_bot.middleware import LanguageMiddleware
from admin_bot.api_server import get_api_server
from shared.database.engine import init_db
from shared.utils.logging import setup_logging as setup_unified_logging
from shared.utils.error_handler import set_error_handler_bot


## Настройка логирования
def setup_logging():
    """
    Настраивает централизованную систему логирования для Admin Bot.
    """
    return setup_unified_logging(
        service_name="admin_bot",
        log_level=settings.log_level,
        console=True,
        file_logging=True
    )


## Инициализация бота и диспетчера
async def init_bot() -> tuple[Bot, Dispatcher]:
    """
    Инициализирует экземпляры Bot и Dispatcher.
    
    Returns:
        Кортеж (Bot, Dispatcher)
    """
    logger = logging.getLogger(__name__)
    
    # Создаём бота с HTML parse mode по умолчанию
    bot = Bot(
        token=settings.admin_bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )
    
    # Создаём диспетчер с хранилищем FSM в памяти
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    
    # Подключаем middleware для языка
    dispatcher.update.middleware(LanguageMiddleware())

    # Подключаем роутеры с хендлерами
    main_router = setup_handlers()
    dispatcher.include_router(main_router)
    
    logger.info("✅ Bot и Dispatcher инициализированы")
    logger.info(f"🤖 Bot: @{(await bot.get_me()).username}")
    logger.info(f"👤 Оператор ID: {settings.operator_user_id}")
    
    return bot, dispatcher


## Обработчик старта бота
async def on_startup(bot: Bot, api_runner):
    """
    Выполняется при старте бота.
    
    Args:
        bot: Экземпляр Bot
        api_runner: Runner для API сервера
    """
    logger = logging.getLogger(__name__)
    
    # Настраиваем error handler
    set_error_handler_bot(bot)
    logger.info("✅ Error handler настроен")
    
    # Создаём папку sessions если её нет
    sessions_dir = settings.sessions_dir
    sessions_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ Папка sessions готова: {sessions_dir}")
    
    # Инициализируем базу данных
    logger.info("🔄 Инициализация базы данных...")
    try:
        await init_db()
        logger.info("✅ База данных готова")
    except Exception as e:
        logger.critical(f"❌ Не удалось инициализировать БД: {e}")
        raise
    
    ## Регистрация команд в меню бота (мультиязычные)
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="leads", description="Список лидов"),
        BotCommand(command="help", description="Справка"),
    ], language_code="ru")
    await bot.set_my_commands([
        BotCommand(command="start", description="Main menu"),
        BotCommand(command="leads", description="Lead list"),
        BotCommand(command="help", description="Help"),
    ], language_code="en")
    logger.info("✅ Команды бота зарегистрированы (RU/EN)")

    logger.info("✅ Admin Bot готов к работе")


## Обработчик остановки бота
async def on_shutdown(bot: Bot):
    """
    Выполняется при остановке бота.
    
    Args:
        bot: Экземпляр Bot
    """
    logger = logging.getLogger(__name__)
    
    logger.info("👋 Admin Bot остановлен")


## Главная функция запуска
async def main():
    """
    Главная функция запуска Admin Bot с API сервером.
    """
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("🚀 Запуск LeadHunter Admin Bot")
    logger.info("=" * 60)
    
    # Валидируем конфигурацию
    try:
        validate_config()
    except Exception as e:
        logger.critical(f"❌ Ошибка конфигурации: {e}")
        sys.exit(1)
    
    # Инициализируем бота
    bot, dispatcher = await init_bot()
    
    # Запускаем API сервер
    api_server = get_api_server(bot)
    api_runner = None
    
    try:
        api_runner = await api_server.start(host='0.0.0.0', port=8000)
        logger.info("✅ API сервер запущен на порту 8000")
    except Exception as e:
        logger.error(f"❌ Не удалось запустить API сервер: {e}")
        # Не критично, продолжаем без API
    
    # Вызываем startup
    await on_startup(bot, api_runner)
    
    # Запускаем polling
    try:
        logger.info("🔄 Запуск polling...")
        logger.info("=" * 60)
        
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=True  # Пропускаем старые обновления при старте
        )
        
    except KeyboardInterrupt:
        logger.info("⚠️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Вызываем shutdown
        await on_shutdown(bot)
        
        # Останавливаем API сервер
        if api_runner:
            await api_server.stop(api_runner)
        
        # Закрываем соединение с ботом
        await bot.session.close()
        logger.info("🔌 Соединение закрыто")


## Точка входа
if __name__ == "__main__":
    # Настраиваем логирование
    setup_logging()
    
    # Запускаем бота
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при запуске: {e}")
        sys.exit(1)

