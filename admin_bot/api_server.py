"""
## HTTP API сервер для Admin Bot
Принимает уведомления от Lead Listener о новых лидах.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from aiohttp import web
from aiogram import Bot

from config import settings
from shared.database.engine import get_session
from shared.database.crud import get_lead_by_id, get_operator_language
from admin_bot.lead_card import format_lead_card, get_lead_push_keyboard


logger = logging.getLogger(__name__)


## HTTP API сервер для приёма уведомлений
class AdminBotAPIServer:
    """
    HTTP сервер для взаимодействия Lead Listener с Admin Bot.
    Принимает уведомления о новых лидах.
    """
    
    def __init__(self, bot: Bot):
        self.app = web.Application()
        self.bot = bot
        self._setup_routes()
        
    def _setup_routes(self):
        """Настройка маршрутов API"""
        self.app.router.add_post('/api/new_lead', self.handle_new_lead)
        self.app.router.add_get('/api/health', self.handle_health)
        self.app.router.add_get('/api/status', self.handle_status)
        
    async def handle_new_lead(self, request: web.Request) -> web.Response:
        """
        Обработчик POST /api/new_lead
        Получает уведомление о новом лиде от Lead Listener.
        
        Ожидаемый JSON:
        {
            "lead_id": 123
        }
        """
        try:
            data = await request.json()
            
            # Валидация
            if 'lead_id' not in data:
                return web.json_response(
                    {'success': False, 'error': 'Missing lead_id'},
                    status=400
                )
            
            lead_id = data['lead_id']
            logger.info(f"📨 Получено уведомление о новом лиде #{lead_id}")
            
            # Отправляем лид-карточку оператору
            await self._send_lead_to_operator(lead_id)
            
            return web.json_response({
                'success': True,
                'message': f'Lead #{lead_id} sent to operator'
            })
            
        except ValueError as e:
            logger.error(f"❌ Ошибка валидации данных: {e}")
            return web.json_response(
                {'success': False, 'error': str(e)},
                status=400
            )
        except Exception as e:
            logger.exception(f"❌ Непредвиденная ошибка в handle_new_lead: {e}")
            return web.json_response(
                {'success': False, 'error': 'Internal server error'},
                status=500
            )
    
    async def _send_lead_to_operator(self, lead_id: int):
        """
        Отправка лид-карточки оператору.
        
        Args:
            lead_id: ID лида
        """
        try:
            async with get_session() as session:
                # Получаем лид
                lead = await get_lead_by_id(session, lead_id, load_relations=True)
                
                if not lead:
                    logger.error(f"❌ Лид #{lead_id} не найден в БД")
                    return
                
                ## AI-данные уже загружены через load_relations
                ai_data = lead.ai_data

                ## Получаем язык оператора
                lang = await get_operator_language(session, settings.operator_user_id)

                # Формируем карточку лида
                text = format_lead_card(lead, ai_data, lang=lang)
                has_draft = bool(lead.draft_reply or (ai_data and ai_data.generated_reply))
                keyboard = get_lead_push_keyboard(lead.id, has_draft=has_draft, lang=lang)
                
                # Отправляем оператору
                try:
                    await self.bot.send_message(
                        chat_id=settings.operator_user_id,
                        text=text,
                        reply_markup=keyboard
                    )
                    logger.info(f"✅ Лид-карточка #{lead_id} отправлена оператору")
                    
                except Exception as send_error:
                    logger.error(f"❌ Не удалось отправить лид оператору: {send_error}")
                    
        except Exception as e:
            logger.exception(f"❌ Ошибка отправки лида оператору: {e}")
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """
        Обработчик GET /api/health
        Проверка работоспособности сервиса.
        """
        return web.json_response({
            'status': 'ok',
            'service': 'admin_bot',
            'timestamp': datetime.utcnow().isoformat()
        })
    
    async def handle_status(self, request: web.Request) -> web.Response:
        """
        Обработчик GET /api/status
        Получение статуса Admin Bot.
        """
        try:
            bot_info = await self.bot.get_me()
            
            return web.json_response({
                'success': True,
                'bot': {
                    'id': bot_info.id,
                    'username': bot_info.username,
                    'first_name': bot_info.first_name
                },
                'operator_id': settings.operator_user_id,
                'timestamp': datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.exception(f"❌ Ошибка получения статуса: {e}")
            return web.json_response(
                {'success': False, 'error': str(e)},
                status=500
            )
    
    async def start(self, host: str = '0.0.0.0', port: int = 8000):
        """
        Запустить API сервер.
        
        Args:
            host: Хост для прослушивания
            port: Порт для прослушивания
        """
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"🚀 Admin Bot API сервер запущен на http://{host}:{port}")
        
        # Возвращаем runner для корректного shutdown
        return runner
    
    async def stop(self, runner: web.AppRunner):
        """
        Остановить API сервер.
        
        Args:
            runner: AppRunner от aiohttp
        """
        await runner.cleanup()
        logger.info("🛑 Admin Bot API сервер остановлен")


## Глобальный экземпляр API сервера
_api_server_instance: Optional[AdminBotAPIServer] = None


def get_api_server(bot: Bot) -> AdminBotAPIServer:
    """
    Получение экземпляра API сервера.
    
    Args:
        bot: Экземпляр Bot
        
    Returns:
        Экземпляр AdminBotAPIServer
    """
    global _api_server_instance
    
    if _api_server_instance is None:
        _api_server_instance = AdminBotAPIServer(bot)
    
    return _api_server_instance

