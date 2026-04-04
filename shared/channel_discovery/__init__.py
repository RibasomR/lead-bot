"""
## Модуль автопоиска и рекомендаций каналов (Фаза 7)
Включает в себя провайдеры поиска через Telegram и TGStat,
а также сервисы для сбора и нормализации данных о каналах.
"""

from shared.channel_discovery.search_service import ChannelDiscoveryService
from shared.channel_discovery.telegram_provider import TelegramSearchProvider

__all__ = [
    "ChannelDiscoveryService",
    "TelegramSearchProvider",
]

