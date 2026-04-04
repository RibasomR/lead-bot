"""
## Модуль антиспам лимитов
Контролирует частоту отправки сообщений для предотвращения банов.
"""

from typing import Dict, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from loguru import logger

from config import settings


## Класс для контроля лимитов отправки
class RateLimiter:
    """
    Отслеживает количество отправленных сообщений в каждый чат.
    Блокирует отправку при превышении лимитов.
    """
    
    def __init__(self):
        # Словарь: chat_tg_id -> список timestamp'ов отправок
        self.send_history: Dict[int, list] = defaultdict(list)
        self.max_per_hour = settings.max_replies_per_chat_per_hour
        
    async def can_send_to_chat(self, chat_tg_id: int) -> Tuple[bool, float]:
        """
        Проверить, можно ли отправить сообщение в чат.
        
        Args:
            chat_tg_id: Telegram ID чата
            
        Returns:
            Tuple[can_send, wait_seconds]
            - can_send: True если можно отправлять
            - wait_seconds: Сколько секунд нужно ждать (если can_send=False)
        """
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        
        # Получаем историю отправок в этот чат
        history = self.send_history[chat_tg_id]
        
        # Очищаем старые записи (старше 1 часа)
        history[:] = [ts for ts in history if ts > one_hour_ago]
        
        # Проверяем лимит
        if len(history) < self.max_per_hour:
            return True, 0.0
            
        # Лимит превышен - вычисляем время ожидания
        oldest_send = min(history)
        wait_until = oldest_send + timedelta(hours=1)
        wait_seconds = (wait_until - now).total_seconds()
        
        logger.debug(
            f"⏳ Лимит для чата {chat_tg_id}: {len(history)}/{self.max_per_hour}. "
            f"Ожидание: {wait_seconds:.0f} сек"
        )
        
        return False, max(0, wait_seconds)
        
    async def register_send(self, chat_tg_id: int):
        """
        Зарегистрировать отправку сообщения в чат.
        
        Args:
            chat_tg_id: Telegram ID чата
        """
        now = datetime.utcnow()
        self.send_history[chat_tg_id].append(now)
        
        logger.debug(
            f"📊 Зарегистрирована отправка в чат {chat_tg_id}. "
            f"Всего за час: {len(self.send_history[chat_tg_id])}/{self.max_per_hour}"
        )
        
    def get_chat_stats(self, chat_tg_id: int) -> Dict:
        """
        Получить статистику отправок для чата.
        
        Args:
            chat_tg_id: Telegram ID чата
            
        Returns:
            Словарь со статистикой
        """
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        
        history = self.send_history.get(chat_tg_id, [])
        recent_sends = [ts for ts in history if ts > one_hour_ago]
        
        return {
            'chat_tg_id': chat_tg_id,
            'sends_last_hour': len(recent_sends),
            'max_per_hour': self.max_per_hour,
            'remaining': max(0, self.max_per_hour - len(recent_sends))
        }
        
    def reset_chat(self, chat_tg_id: int):
        """
        Сбросить историю отправок для чата.
        
        Args:
            chat_tg_id: Telegram ID чата
        """
        if chat_tg_id in self.send_history:
            del self.send_history[chat_tg_id]
            logger.info(f"🔄 История отправок для чата {chat_tg_id} сброшена")

