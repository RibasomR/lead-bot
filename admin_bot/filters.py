"""
## Фильтры для Admin Bot
Пользовательские фильтры для обработки сообщений и callback-запросов.
"""

from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from config import settings


## Фильтр доступа только для оператора
class OperatorFilter(BaseFilter):
    """
    Фильтр, пропускающий только сообщения от оператора.
    Проверяет user_id отправителя против OPERATOR_USER_ID из конфига.
    """
    
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        """
        Проверяет, является ли отправитель оператором.
        
        Args:
            event: Событие Telegram (Message или CallbackQuery)
            
        Returns:
            True, если отправитель - оператор, иначе False
        """
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
        else:
            return False
            
        return user_id == settings.operator_user_id

