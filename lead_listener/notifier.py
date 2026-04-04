"""
## Модуль отправки уведомлений в Admin Bot
Отправляет уведомления о новых лидах через HTTP API.
"""

from typing import Optional
from loguru import logger
import httpx

from config import settings


## Класс для отправки уведомлений в Admin Bot
class AdminBotNotifier:
    """
    Отправляет уведомления о новых лидах в Admin Bot через HTTP API.
    """
    
    def __init__(self):
        self.admin_bot_url = settings.admin_bot_api_url
        self.http_client = httpx.AsyncClient(timeout=10.0)
        self.enabled = bool(self.admin_bot_url)
        
        if self.enabled:
            logger.info(f"📡 AdminBotNotifier: API URL = {self.admin_bot_url}")
        else:
            logger.warning("⚠️ AdminBotNotifier: URL не настроен, уведомления отключены")
        
    async def notify_new_lead(self, lead_id: int) -> bool:
        """
        Отправить уведомление о новом лиде в Admin Bot.
        
        Args:
            lead_id: ID нового лида
            
        Returns:
            True если уведомление отправлено успешно
        """
        logger.info(f"📨 Новый лид #{lead_id} создан")
        
        # Если URL не настроен, просто логируем
        if not self.enabled:
            logger.debug("Admin Bot API не настроен, пропускаем уведомление")
            return True
        
        try:
            # Отправляем HTTP запрос в Admin Bot
            response = await self.http_client.post(
                f"{self.admin_bot_url}/api/new_lead",
                json={'lead_id': lead_id},
                timeout=5.0
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Уведомление о лиде #{lead_id} отправлено в Admin Bot")
                return True
            else:
                logger.warning(
                    f"⚠️ Admin Bot вернул статус {response.status_code} для лида #{lead_id}"
                )
                return False
                
        except httpx.TimeoutException:
            logger.error(f"❌ Таймаут при отправке уведомления о лиде #{lead_id}")
            return False
        except httpx.ConnectError:
            logger.error(
                f"❌ Не удалось подключиться к Admin Bot ({self.admin_bot_url}). "
                f"Лид #{lead_id} создан, но уведомление не отправлено."
            )
            return False
        except Exception as e:
            logger.exception(f"❌ Непредвиденная ошибка при отправке уведомления о лиде #{lead_id}: {e}")
            return False
            
    async def check_health(self) -> bool:
        """
        Проверка доступности Admin Bot API.
        
        Returns:
            True если API доступен
        """
        if not self.enabled:
            return False
        
        try:
            response = await self.http_client.get(
                f"{self.admin_bot_url}/api/health",
                timeout=3.0
            )
            
            if response.status_code == 200:
                logger.info("✅ Admin Bot API доступен")
                return True
            else:
                logger.warning(f"⚠️ Admin Bot API вернул статус {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Admin Bot API недоступен: {e}")
            return False
            
    async def close(self):
        """Закрыть HTTP клиент"""
        await self.http_client.aclose()
        logger.info("🔌 AdminBotNotifier HTTP клиент закрыт")

