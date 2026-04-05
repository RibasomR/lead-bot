"""
## Middleware для Admin Bot
LanguageMiddleware — извлекает язык оператора из БД и кладёт в data["lang"].
"""

from typing import Callable, Awaitable, Any, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from shared.database.engine import get_session
from shared.database.crud import get_operator_language


class LanguageMiddleware(BaseMiddleware):
    """
    На каждый запрос достаёт язык оператора из БД.
    Кладёт в data["lang"] ("ru" / "en"). Fallback — "ru".
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None

        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        lang = "ru"
        if user_id:
            try:
                async with get_session() as session:
                    lang = await get_operator_language(session, user_id)
            except Exception:
                pass

        data["lang"] = lang
        return await handler(event, data)
