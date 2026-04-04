"""
## HTTP API сервер для Lead Listener
Принимает команды от Admin Bot для отправки сообщений через userbot.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from loguru import logger

from config import settings
from shared.database.engine import get_session
from shared.database.crud import (
    get_account_by_id, get_chat_by_tg_id, create_reply
)
from lead_listener.sender import MessageSender
from lead_listener.rate_limiter import RateLimiter


## HTTP API сервер для приёма команд отправки
class APIServer:
    """
    HTTP сервер для взаимодействия Admin Bot с Lead Listener.
    Принимает команды отправки сообщений через userbot.
    """
    
    def __init__(self, message_sender: MessageSender, notifier=None):
        self.app = web.Application()
        self.message_sender = message_sender
        self.notifier = notifier
        self.rate_limiter = RateLimiter()
        self._setup_routes()
        self._setup_error_handlers()
    
    def _setup_error_handlers(self):
        """
        ## Настройка обработчиков ошибок для некорректных HTTP запросов
        Обработка ошибок происходит через фильтр логирования в методе start()
        """
        pass
        
    def _setup_routes(self):
        """Настройка маршрутов API"""
        self.app.router.add_post('/api/send_message', self.handle_send_message)
        self.app.router.add_get('/api/health', self.handle_health)
        self.app.router.add_get('/api/accounts/status', self.handle_accounts_status)
        self.app.router.add_post('/api/discover_channels', self.handle_discover_channels)  ## Фаза 7.3 (deprecated)
        self.app.router.add_post('/api/search_global', self.handle_search_global)  ## Глобальный поиск (v2)
        self.app.router.add_post('/api/join_all_chats', self.handle_join_all_chats)  ## Автоподписка на все enabled чаты
        self.app.router.add_post('/api/get_chat_info', self.handle_get_chat_info)  ## Получение информации о чате
        
    async def handle_send_message(self, request: web.Request) -> web.Response:
        """
        Обработчик POST /api/send_message
        
        Ожидаемый JSON:
        {
            "lead_id": 123,
            "account_id": 1,
            "chat_tg_id": -1001234567890,
            "message_text": "Здравствуйте! ...",
            "style_used": "friendly",
            "reply_to_message_id": 45678,
            "author_username": "username_заказчика"  # Опционально, для отправки в личку
        }
        """
        try:
            data = await request.json()
            
            # Валидация обязательных полей
            required_fields = ['lead_id', 'account_id', 'chat_tg_id', 'message_text', 'style_used']
            for field in required_fields:
                if field not in data:
                    return web.json_response(
                        {'success': False, 'error': f'Missing required field: {field}'},
                        status=400
                    )
                    
            lead_id = data['lead_id']
            account_id = data['account_id']
            chat_tg_id = data['chat_tg_id']
            message_text = data['message_text']
            style_used = data['style_used']
            reply_to_message_id = data.get('reply_to_message_id')
            author_username = data.get('author_username')  ## Username заказчика для отправки в личку
            author_id = data.get('author_id')  ## Telegram User ID автора
            
            # Проверка лимитов антиспама
            can_send, wait_time = await self.rate_limiter.can_send_to_chat(chat_tg_id)
            
            if not can_send:
                logger.warning(
                    f"⚠️ Превышен лимит отправок для чата {chat_tg_id}. "
                    f"Ожидание: {wait_time:.0f} сек"
                )
                return web.json_response({
                    'success': False,
                    'error': 'Rate limit exceeded',
                    'wait_seconds': int(wait_time)
                }, status=429)
                
            # Отправка сообщения в ЛС заказчику
            success, error_msg = await self.message_sender.send_message(
                account_id=account_id,
                chat_tg_id=chat_tg_id,
                message_text=message_text,
                reply_to_message_id=reply_to_message_id,
                author_username=author_username,
                author_id=author_id,
            )
            
            # Логирование в БД
            async with get_session() as session:
                await create_reply(
                    session=session,
                    lead_id=lead_id,
                    account_id=account_id,
                    style_used=style_used,
                    reply_text=message_text,
                    was_successful=success,
                    error_message=error_msg if not success else None
                )
                await session.commit()
                
            if success:
                # Регистрируем отправку для антиспама
                await self.rate_limiter.register_send(chat_tg_id)
                
                logger.info(
                    f"✅ Сообщение отправлено: лид #{lead_id}, "
                    f"аккаунт #{account_id}, чат {chat_tg_id}"
                )
                
                return web.json_response({
                    'success': True,
                    'message': 'Message sent successfully'
                })
            else:
                logger.error(
                    f"❌ Ошибка отправки: лид #{lead_id}, "
                    f"аккаунт #{account_id}: {error_msg}"
                )
                
                return web.json_response({
                    'success': False,
                    'error': error_msg
                }, status=500)
                
        except ValueError as e:
            logger.error(f"❌ Ошибка валидации данных: {e}")
            return web.json_response(
                {'success': False, 'error': str(e)},
                status=400
            )
        except Exception as e:
            logger.exception(f"❌ Непредвиденная ошибка в handle_send_message: {e}")
            return web.json_response(
                {'success': False, 'error': 'Internal server error'},
                status=500
            )
            
    async def handle_health(self, request: web.Request) -> web.Response:
        """
        Обработчик GET /api/health
        Проверка работоспособности сервиса.
        """
        return web.json_response({
            'status': 'ok',
            'service': 'lead_listener',
            'timestamp': datetime.utcnow().isoformat()
        })
        
    async def handle_accounts_status(self, request: web.Request) -> web.Response:
        """
        Обработчик GET /api/accounts/status
        Получение статуса всех аккаунтов.
        """
        try:
            status = self.message_sender.get_accounts_status()
            
            return web.json_response({
                'success': True,
                'accounts': status
            })
        except Exception as e:
            logger.exception(f"❌ Ошибка получения статуса аккаунтов: {e}")
            return web.json_response(
                {'success': False, 'error': str(e)},
                status=500
            )
    
    async def handle_discover_channels(self, request: web.Request) -> web.Response:
        """
        ## Обработчик POST /api/discover_channels (Фаза 7.3)
        Запускает автопоиск каналов через Telethon.
        
        Ожидаемый JSON:
        {
            "custom_queries": ["боты python", "фриланс"],  # Опционально
            "limit_per_query": 10,                         # Опционально
            "evaluate_with_ai": true                       # Опционально
        }
        """
        try:
            data = await request.json() if request.body_exists else {}
            
            custom_queries = data.get('custom_queries')
            limit_per_query = data.get('limit_per_query', 10)
            evaluate_with_ai = data.get('evaluate_with_ai', True)
            
            # Получаем первый доступный userbot клиент
            if not self.message_sender.client_manager.clients:
                return web.json_response({
                    'success': False,
                    'error': 'No userbot clients available'
                }, status=503)
            
            # Берём первый клиент для поиска
            first_client = list(self.message_sender.client_manager.clients.values())[0]
            
            # Импортируем необходимые модули
            from shared.channel_discovery import ChannelDiscoveryService, TelegramSearchProvider
            
            # Создаём провайдер и сервис
            telegram_provider = TelegramSearchProvider(first_client)
            
            async with get_session() as session:
                service = ChannelDiscoveryService(
                    telegram_provider=telegram_provider,
                    db_session=session
                )
                
                # Запускаем поиск
                logger.info(f"🔍 Запуск автопоиска каналов (лимит: {limit_per_query}, AI: {evaluate_with_ai})")
                
                candidate_ids = await service.discover_channels(
                    custom_queries=custom_queries,
                    limit_per_query=limit_per_query,
                    evaluate_with_ai=evaluate_with_ai
                )
                
                logger.info(f"✅ Автопоиск завершён: найдено {len(candidate_ids)} каналов")
            
            return web.json_response({
                'success': True,
                'candidate_ids': candidate_ids,
                'count': len(candidate_ids)
            })
        
        except Exception as e:
            logger.exception(f"❌ Ошибка автопоиска каналов: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
            
    async def handle_search_global(self, request: web.Request) -> web.Response:
        """
        ## Обработчик POST /api/search_global (v2)
        Запускает глобальный поиск заказов через Telegram search_global.

        Ожидаемый JSON (все поля опциональны):
        {
            "query_text": "нужен бот"  # Конкретный запрос (если None — все активные)
        }
        """
        try:
            data = await request.json() if request.body_exists else {}
            query_text = data.get("query_text")

            ## Нужен хотя бы один клиент
            if not self.message_sender.client_manager.clients:
                return web.json_response({
                    "success": False,
                    "error": "No userbot clients available"
                }, status=503)

            ## Берём первый клиент и его account_id
            first_account_id = list(self.message_sender.client_manager.clients.keys())[0]
            first_client = self.message_sender.client_manager.clients[first_account_id]

            from lead_listener.global_search import GlobalSearcher
            searcher = GlobalSearcher(first_client, first_account_id, notifier=self.notifier)

            if query_text:
                stats = await searcher.run_single_query(query_text)
            else:
                stats = await searcher.run_all_queries()

            logger.info(f"✅ Глобальный поиск завершён: {stats}")

            return web.json_response({
                "success": True,
                "stats": stats
            })

        except Exception as e:
            logger.exception(f"❌ Ошибка глобального поиска: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def start(self, host: str = '0.0.0.0', port: int = 8001):
        """
        Запустить API сервер.
        
        Args:
            host: Хост для прослушивания
            port: Порт для прослушивания
        """
        ## Настройка подавления некорректных HTTP запросов в логах
        # Эти ошибки возникают от сканеров портов и попыток HTTPS подключения
        # Настраиваем логирование aiohttp для подавления BadStatusLine ошибок
        aiohttp_logger = logging.getLogger('aiohttp')
        aiohttp_web_logger = logging.getLogger('aiohttp.web')
        aiohttp_access_logger = logging.getLogger('aiohttp.access')
        
        # Фильтр для подавления BadStatusLine и некорректных HTTP запросов
        class BadRequestFilter(logging.Filter):
            def filter(self, record):
                # Подавляем ошибки некорректных HTTP запросов (сканеры, HTTPS попытки)
                msg = record.getMessage() if hasattr(record, 'getMessage') else str(record.msg)
                
                # Проверяем на BadStatusLine ошибки
                if 'BadStatusLine' in msg or 'Invalid method' in msg:
                    # Не логируем эти ошибки (возвращаем False)
                    return False
                
                # Проверяем на попытки HTTPS подключения (TLS handshake)
                if '\\x16\\x03\\x01' in msg or 'Invalid method encountered' in msg:
                    return False
                    
                return True
        
        bad_request_filter = BadRequestFilter()
        aiohttp_logger.addFilter(bad_request_filter)
        aiohttp_web_logger.addFilter(bad_request_filter)
        aiohttp_access_logger.addFilter(bad_request_filter)
        
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"🚀 API сервер запущен на http://{host}:{port}")
        
        # Возвращаем runner для корректного shutdown
        return runner
        
    async def stop(self, runner: web.AppRunner):
        """
        Остановить API сервер.
        
        Args:
            runner: AppRunner от aiohttp
        """
        await runner.cleanup()
        logger.info("🛑 API сервер остановлен")
    
    async def handle_get_chat_info(self, request: web.Request) -> web.Response:
        """
        ## Обработчик POST /api/get_chat_info
        Получает информацию о чате по Chat ID, username или ссылке через Telethon.
        
        Ожидаемый JSON:
        {
            "identifier": "-1001234567890" или "@pythonru" или "https://t.me/pythonru"
        }
        
        Возвращает:
        {
            "success": true,
            "chat_id": -1001234567890,
            "title": "Python Ru",
            "type": "supergroup",
            "username": "pythonru"
        }
        """
        try:
            data = await request.json()
            identifier = data.get('identifier')
            
            if not identifier:
                return web.json_response({
                    'success': False,
                    'error': 'Missing identifier field'
                }, status=400)
            
            # Получаем первый доступный userbot клиент
            if not self.message_sender.client_manager.clients:
                return web.json_response({
                    'success': False,
                    'error': 'No userbot clients available'
                }, status=503)
            
            # Берём первый клиент для запроса
            first_client = list(self.message_sender.client_manager.clients.values())[0]
            
            ## Проверяем что клиент подключён и авторизован
            if not first_client.is_connected():
                logger.error("❌ Telethon клиент не подключён")
                return web.json_response({
                    'success': False,
                    'error': 'Userbot client is not connected. Please restart the Lead Listener service.'
                }, status=503)
            
            if not await first_client.is_user_authorized():
                logger.error("❌ Telethon клиент не авторизован")
                return web.json_response({
                    'success': False,
                    'error': 'Userbot client is not authorized. Please authorize via CLI.'
                }, status=503)
            
            logger.info(f"🔍 Получение информации о чате: {identifier}")
            
            # Парсим идентификатор (поддержка ссылок t.me/)
            chat_identifier = identifier
            
            # Если это ссылка t.me/ — извлекаем username
            if 't.me/' in identifier or 'telegram.me/' in identifier:
                # Парсим ссылку: https://t.me/vibecoderchat или t.me/vibecoderchat
                parts = identifier.replace('https://', '').replace('http://', '').split('/')
                if len(parts) >= 2:
                    username = parts[-1].split('?')[0]  # Убираем query params если есть
                    chat_identifier = username if username.startswith('@') else f'@{username}'
                    logger.debug(f"💡 Извлечён username из ссылки: {chat_identifier}")
            elif identifier.startswith('-'):
                # Chat ID (преобразуем в int)
                try:
                    chat_identifier = int(identifier)
                except ValueError:
                    return web.json_response({
                        'success': False,
                        'error': 'Invalid Chat ID format'
                    }, status=400)
            elif not identifier.startswith('@'):
                # Если это просто username без @ — добавляем @
                chat_identifier = f'@{identifier}'
                logger.debug(f"💡 Добавлен @ к username: {chat_identifier}")
            
            # Получаем информацию о чате через Telethon
            try:
                from telethon.tl.types import Channel, Chat, User
                from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError
                
                ## Используем get_entity - более надёжный метод чем ResolveUsernameRequest
                logger.debug(f"🔍 Получение entity для: {chat_identifier}")
                
                try:
                    entity = await first_client.get_entity(chat_identifier)
                    
                    # Проверяем что это не пользователь
                    if isinstance(entity, User):
                        logger.warning(f"⚠️ {chat_identifier} это пользователь, а не чат/канал")
                        return web.json_response({
                            'success': False,
                            'error': 'This is a user, not a chat/channel'
                        }, status=400)
                            
                except (UsernameNotOccupiedError, UsernameInvalidError, ValueError) as e:
                    logger.warning(f"⚠️ Чат/канал не найден: {chat_identifier} - {e}")
                    return web.json_response({
                        'success': False,
                        'error': f'Chat/channel not found: {str(e)}'
                    }, status=404)
                
                # Извлекаем информацию
                chat_id = entity.id if hasattr(entity, 'id') else None
                title = entity.title if hasattr(entity, 'title') else None
                username = entity.username if hasattr(entity, 'username') else None
                
                # Определяем тип
                if isinstance(entity, Channel):
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        chat_type = "supergroup"
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        chat_type = "channel"
                    else:
                        chat_type = "group"
                elif isinstance(entity, Chat):
                    chat_type = "group"
                else:
                    chat_type = "unknown"
                
                logger.info(f"✅ Информация получена: {title} ({chat_type})")
                
                return web.json_response({
                    'success': True,
                    'chat_id': chat_id,
                    'title': title or "Без названия",
                    'type': chat_type,
                    'username': username
                })
                
            except ValueError as e:
                # Чат не найден или недоступен
                logger.warning(f"⚠️ Чат не найден: {identifier} | {e}")
                return web.json_response({
                    'success': False,
                    'error': f'Chat not found or not accessible: {str(e)}'
                }, status=404)
            except Exception as e:
                # Другие ошибки Telethon
                error_msg = str(e)
                logger.error(f"❌ Telethon error для {identifier}: {error_msg}")
                
                ## Улучшенная диагностика ошибок
                if 'not registered' in error_msg.lower() or 'auth key' in error_msg.lower():
                    return web.json_response({
                        'success': False,
                        'error': 'Userbot session is not properly authorized. Please restart Lead Listener and ensure all accounts are authorized via CLI.'
                    }, status=503)
                elif 'flood' in error_msg.lower():
                    return web.json_response({
                        'success': False,
                        'error': 'Telegram rate limit reached. Please try again later.'
                    }, status=429)
                else:
                    return web.json_response({
                        'success': False,
                        'error': f'Telegram API error: {error_msg}'
                    }, status=500)
                
        except Exception as e:
            logger.exception(f"❌ Ошибка получения информации о чате: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def handle_join_all_chats(self, request: web.Request) -> web.Response:
        """
        ## Обработчик POST /api/join_all_chats
        Подписка monitor-аккаунтов на все активные чаты (reply-аккаунты не вступают).
        """
        try:
            logger.info("🔄 Запущена подписка monitor-аккаунтов на все enabled чаты...")
            
            # Получаем все enabled чаты
            from shared.database.engine import get_session
            from shared.database.crud import get_all_chats
            
            async with get_session() as session:
                enabled_chats = await get_all_chats(
                    session,
                    enabled_only=True,
                    exclude_blacklisted=True
                )
                
                if not enabled_chats:
                    return web.json_response({
                        'success': False,
                        'error': 'Нет активных чатов для подписки'
                    }, status=404)
                
                logger.info(f"📋 Найдено {len(enabled_chats)} активных чатов")
                
                # Запускаем подписку через ClientManager
                results = await self.message_sender.client_manager.join_chats(enabled_chats)
                
                # Форматируем результаты для ответа
                return web.json_response({
                    'success': True,
                    'total_chats': len(enabled_chats),
                    'results': {
                        'success': len(results['success']),
                        'already_joined': len(results['already_joined']),
                        'errors': len(results['errors']),
                        'private': len(results['private']),
                        'flood_wait': len(results['flood_wait'])
                    },
                    'details': results
                })
                
        except Exception as e:
            logger.exception(f"❌ Ошибка автоподписки на все чаты: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

