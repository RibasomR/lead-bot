"""
## Опциональный провайдер обогащения данных через TGStat API
Используется только если в .env указан TGSTAT_API_KEY.
Добавляет расширенную статистику и метрики к каналам.
"""

import logging
from typing import Optional, Dict, Any, List
import httpx

from config import settings

logger = logging.getLogger(__name__)


## Провайдер TGStat
class TGStatProvider:
    """
    Опциональный провайдер для обогащения данных о каналах через TGStat API.
    Активируется только при наличии API ключа.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация провайдера TGStat
        
        Args:
            api_key: API ключ TGStat (если None, берётся из settings)
        """
        self.api_key = api_key or settings.tgstat_api_key
        self.base_url = "https://api.tgstat.ru"
        self.is_enabled = bool(self.api_key)
        
        if not self.is_enabled:
            logger.info("ℹ️ TGStat провайдер отключен (нет API ключа)")
        else:
            logger.info("✅ TGStat провайдер активирован")
    
    async def enrich_channel_data(
        self,
        username: str
    ) -> Optional[Dict[str, Any]]:
        """
        ## Получение расширенных данных о канале из TGStat
        
        Args:
            username: Username канала без @
            
        Returns:
            Словарь с метриками или None
        """
        if not self.is_enabled:
            return None
        
        try:
            # Убираем @ если есть
            clean_username = username.lstrip('@')
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Запрос к TGStat API
                response = await client.get(
                    f"{self.base_url}/channels/get",
                    params={
                        "token": self.api_key,
                        "channelId": f"@{clean_username}"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "ok":
                        channel_info = data.get("response", {})
                        
                        # Извлекаем полезные метрики
                        enriched_data = {
                            "members_count": channel_info.get("participants_count"),
                            "avg_post_reach": channel_info.get("avg_post_reach"),
                            "err": channel_info.get("err"),  # ERR - engagement rate
                            "mentions_count": channel_info.get("mentions_count"),
                            "category": channel_info.get("category"),
                            "language": channel_info.get("language"),
                            "verified": channel_info.get("verified", False)
                        }
                        
                        logger.debug(f"✅ TGStat: получены данные для @{clean_username}")
                        return enriched_data
                    else:
                        logger.warning(f"⚠️ TGStat: {data.get('error', 'Unknown error')}")
                        return None
                else:
                    logger.warning(f"⚠️ TGStat вернул статус {response.status_code}")
                    return None
        
        except httpx.TimeoutException:
            logger.error("❌ Таймаут запроса к TGStat API")
            return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе к TGStat: {e}")
            return None
    
    async def search_channels(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        ## Поиск каналов через TGStat API
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            
        Returns:
            Список каналов с метриками
        """
        if not self.is_enabled:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/channels/search",
                    params={
                        "token": self.api_key,
                        "q": query,
                        "limit": limit
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "ok":
                        channels = data.get("response", {}).get("items", [])
                        logger.info(f"🔍 TGStat: найдено {len(channels)} каналов по запросу '{query}'")
                        return channels
                    else:
                        logger.warning(f"⚠️ TGStat search error: {data.get('error')}")
                        return []
                else:
                    logger.warning(f"⚠️ TGStat search вернул статус {response.status_code}")
                    return []
        
        except Exception as e:
            logger.error(f"❌ Ошибка поиска в TGStat: {e}")
            return []
    
    def is_available(self) -> bool:
        """Проверка доступности TGStat провайдера"""
        return self.is_enabled

