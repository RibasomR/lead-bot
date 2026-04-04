"""
## Главный модуль Lead Listener
Userbot-сервис для мониторинга Telegram-чатов и поиска лидов.
Использует Telethon для работы с несколькими клиентами одновременно.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from loguru import logger

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

sys.path.append(str(Path(__file__).parent.parent))

from config import settings
from shared.database.engine import get_session, init_db
from shared.database.crud import get_all_accounts, get_all_chats
from shared.database.models import Account, Chat
from lead_listener.client_manager import ClientManager
from lead_listener.message_handler import MessageHandler
from lead_listener.sender import MessageSender
from lead_listener.api_server import APIServer
from lead_listener.notifier import AdminBotNotifier


## Класс для управления всем сервисом Lead Listener
class LeadListener:
    """
    Основной сервис для мониторинга Telegram-чатов.
    Управляет несколькими Telethon-клиентами и обрабатывает входящие сообщения.
    """
    
    def __init__(self):
        self.notifier = AdminBotNotifier()
        self.client_manager = ClientManager(notifier=self.notifier)
        self.message_sender = MessageSender(self.client_manager)
        self.api_server = APIServer(self.message_sender, notifier=self.notifier)
        self.message_handler = self.client_manager.message_handler
        self.is_running = False
        self.api_runner = None
        
    async def initialize(self):
        """Инициализация сервиса: подключение к БД и загрузка конфигурации"""
        logger.info("🔄 Инициализация Lead Listener...")
        
        # Инициализация БД
        await init_db()
        logger.info("✅ База данных подключена")
        
        # Загрузка аккаунтов из БД
        async with get_session() as session:
            accounts = await get_all_accounts(session, enabled_only=True)
            
            if not accounts:
                logger.warning("⚠️ Нет активных аккаунтов в БД. Ожидание добавления через Admin Bot...")
            else:
                logger.info(f"📋 Найдено {len(accounts)} активных аккаунтов")
                
                # Создание Telethon клиентов для каждого аккаунта
                for account in accounts:
                    await self.client_manager.add_client(account)
                
        logger.info("✅ Lead Listener инициализирован")
        return True
        
    async def _daily_global_search(self):
        """Ежедневный автопоиск лидов через search_global (Premium)."""
        OPERATOR_TZ = timezone(timedelta(hours=7))
        SEARCH_HOUR = 10  ## Запуск в 10:00 по UTC+7

        ## Ждём первого запуска
        await asyncio.sleep(30)  ## даём время клиентам подключиться

        while self.is_running:
            try:
                now = datetime.now(OPERATOR_TZ)
                ## Следующий запуск — сегодня в SEARCH_HOUR или завтра если уже прошло
                target = now.replace(hour=SEARCH_HOUR, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += timedelta(days=1)

                wait_seconds = (target - now).total_seconds()
                logger.info(
                    f"🔍 Следующий автопоиск: {target.strftime('%Y-%m-%d %H:%M')} UTC+7 "
                    f"(через {wait_seconds/3600:.1f}ч)"
                )
                await asyncio.sleep(wait_seconds)

                if not self.is_running:
                    break

                ## Берём monitor-аккаунт для поиска (или первый доступный)
                if not self.client_manager.clients:
                    logger.warning("⚠️ Автопоиск: нет подключённых клиентов")
                    continue

                search_account_id = None
                for acc_id, role in self.client_manager.account_roles.items():
                    if role in ("monitor", "both") and acc_id in self.client_manager.clients:
                        search_account_id = acc_id
                        break
                if search_account_id is None:
                    search_account_id = list(self.client_manager.clients.keys())[0]

                search_client = self.client_manager.clients[search_account_id]

                from lead_listener.global_search import GlobalSearcher
                searcher = GlobalSearcher(search_client, search_account_id, notifier=self.notifier)

                logger.info("🔍 Запуск ежедневного автопоиска...")
                stats = await searcher.run_all_queries()
                logger.info(
                    f"✅ Автопоиск завершён: запросов={stats['queries_executed']}, "
                    f"найдено={stats['total_found']}, лидов={stats['total_leads']}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка автопоиска: {e}")
                await asyncio.sleep(3600)  ## повтор через час при ошибке

    async def start(self):
        """Запуск мониторинга всех клиентов"""
        if not await self.initialize():
            logger.error("❌ Не удалось инициализировать Lead Listener")
            return

        logger.info("🚀 Запуск Lead Listener...")
        self.is_running = True

        try:
            # Запуск API сервера
            self.api_runner = await self.api_server.start(host='0.0.0.0', port=8001)
            logger.info("✅ API сервер запущен")

            # Подключение всех клиентов
            await self.client_manager.connect_all()
            logger.info("✅ Все клиенты подключены")

            # Загрузка чатов для мониторинга
            async with get_session() as session:
                chats = await get_all_chats(session, enabled_only=True)

                if not chats:
                    logger.warning("⚠️ Нет активных чатов для мониторинга")
                else:
                    logger.info(f"📋 Найдено {len(chats)} чатов для мониторинга")

                    # Распределение чатов между клиентами
                    await self.client_manager.subscribe_to_chats(chats)

                    ## Ретроспективная обработка в фоне (не блокирует API и мониторинг)
                    logger.info("🔄 Запуск ретроспективной обработки сообщений (фон)...")
                    asyncio.create_task(
                        self.client_manager.process_recent_messages(chats, days_back=1)
                    )

            ## Автопоиск временно отключён — iter_messages(entity=None) ищет
            ## только по своим чатам, нужна переделка на SearchPostsRequest
            # asyncio.create_task(self._daily_global_search())
            # logger.info("✅ Автопоиск запланирован (ежедневно в 10:00 UTC+7)")

            # Запуск обработки сообщений
            await self.client_manager.run_until_disconnected()
            
        except KeyboardInterrupt:
            logger.info("⚠️ Получен сигнал остановки (Ctrl+C)")
            await self.stop()
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка в Lead Listener: {e}")
            await self.stop()
            
    async def stop(self):
        """Остановка всех клиентов и корректное завершение"""
        logger.info("🛑 Остановка Lead Listener...")
        self.is_running = False
        
        # Остановка API сервера
        if self.api_runner:
            await self.api_server.stop(self.api_runner)
        
        # Отключение всех клиентов
        await self.client_manager.disconnect_all()
        logger.info("✅ Lead Listener остановлен")


## Точка входа в приложение
async def main():
    """Главная функция запуска Lead Listener"""
    # Настройка логирования
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=settings.log_level
    )
    logger.add(
        settings.log_file,
        rotation="10 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level=settings.log_level
    )
    
    logger.info("=" * 60)
    logger.info("🎯 LeadHunter - Lead Listener Service")
    logger.info("=" * 60)
    
    listener = LeadListener()
    await listener.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Выход из программы")
    except Exception as e:
        logger.exception(f"💥 Непредвиденная ошибка: {e}")
        sys.exit(1)

