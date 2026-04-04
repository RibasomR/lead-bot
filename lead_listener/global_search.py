"""
## Глобальный поиск заказов через Telegram Premium search_global (v2)
Поиск по заданным фразам, дедупликация, классификация найденных сообщений.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from telethon import TelegramClient
from sqlalchemy.exc import IntegrityError as SQLIntegrityError

from config import settings
from shared.database.engine import get_session
from shared.database.crud import (
    get_all_search_queries,
    get_todays_search_queries,
    update_search_query_usage,
    create_search_global_result,
    count_search_queries_today,
    get_chat_by_tg_id,
    create_chat,
)
from shared.ai.classifier import get_classifier

logger = logging.getLogger(__name__)

## Лимит запросов в день (API не связан с UI-квотой Telegram)
MAX_SEARCHES_PER_DAY = 15

## Максимум сообщений на один запрос
MAX_RESULTS_PER_QUERY = 20


class GlobalSearcher:
    """
    Глобальный поиск заказов через client.search_global().
    Работает только с Telegram Premium аккаунтами.
    """

    def __init__(self, client: TelegramClient, account_id: int, notifier=None):
        self.client = client
        self.account_id = account_id
        self.classifier = get_classifier()
        self.notifier = notifier

    async def run_all_queries(self) -> Dict[str, Any]:
        """
        Выполнить все активные поисковые запросы.

        Returns:
            Статистика: {total_found, total_leads, queries_executed, errors}
        """
        stats = {
            "total_found": 0,
            "total_leads": 0,
            "queries_executed": 0,
            "errors": [],
        }

        async with get_session() as session:
            ## Проверяем лимит на день
            today_count = await count_search_queries_today(session)
            if today_count >= MAX_SEARCHES_PER_DAY:
                logger.warning(
                    f"⚠️ Лимит поисков на сегодня исчерпан ({today_count}/{MAX_SEARCHES_PER_DAY})"
                )
                stats["errors"].append("Daily search limit reached")
                return stats

            ## Ротация: 10 фраз на сегодня из всего пула
            queries = await get_todays_search_queries(session)

        if not queries:
            logger.info("📭 Нет активных поисковых запросов")
            return stats

        remaining = MAX_SEARCHES_PER_DAY - today_count

        for query in queries[:remaining]:
            try:
                found, leads = await asyncio.wait_for(
                    self._execute_query(query.id, query.query_text),
                    timeout=300,
                )
                stats["total_found"] += found
                stats["total_leads"] += leads
                stats["queries_executed"] += 1

                logger.info(
                    f"🔍 Запрос '{query.query_text}': "
                    f"найдено {found}, лидов {leads}"
                )

                ## Задержка между запросами
                await asyncio.sleep(2.0)

            except Exception as e:
                logger.error(f"❌ Ошибка запроса '{query.query_text}': {e}")
                stats["errors"].append(f"{query.query_text}: {str(e)}")

        return stats

    async def run_single_query(self, query_text: str, query_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Выполнить один поисковый запрос.

        Args:
            query_text: Текст запроса
            query_id: ID запроса в БД (опционально)

        Returns:
            {found, leads, errors}
        """
        try:
            found, leads = await self._execute_query(query_id, query_text)
            return {"found": found, "leads": leads, "errors": []}
        except Exception as e:
            logger.error(f"❌ Ошибка запроса '{query_text}': {e}")
            return {"found": 0, "leads": 0, "errors": [str(e)]}

    async def _ensure_chat_in_db(self, chat_id: int) -> None:
        """Создать запись чата в БД если его нет (enabled=False, не мониторится)."""
        async with get_session() as session:
            existing = await get_chat_by_tg_id(session, chat_id)
            if existing:
                return

            ## Получаем название чата из Telethon
            chat_title = "Unknown"
            chat_type = "group"
            username = None
            try:
                entity = await self.client.get_entity(chat_id)
                chat_title = getattr(entity, "title", None) or getattr(entity, "first_name", "Unknown")
                username = getattr(entity, "username", None)
                if hasattr(entity, "broadcast") and entity.broadcast:
                    chat_type = "channel"
            except Exception:
                pass

            try:
                await create_chat(
                    session=session,
                    tg_chat_id=chat_id,
                    title=chat_title,
                    chat_type=chat_type,
                    username=username,
                    priority=0,
                    is_whitelisted=False,
                    enabled=False,  ## Не мониторим — только для FK в лидах
                )
                await session.commit()
                logger.info(f"📌 Чат '{chat_title}' ({chat_id}) добавлен в БД (search_global, не мониторится)")
            except SQLIntegrityError:
                ## Race condition: чат уже создан другим параллельным вызовом
                await session.rollback()
                logger.debug(f"Чат {chat_id} уже существует (параллельная вставка)")

    async def _execute_query(self, query_id: Optional[int], query_text: str) -> tuple:
        """
        Выполнить поисковый запрос и обработать результаты.

        Args:
            query_id: ID запроса в БД
            query_text: Текст для поиска

        Returns:
            (найдено_сообщений, создано_лидов)
        """
        found = 0
        leads_created = 0

        ## Создаём handler один раз, с notifier для отправки лидов оператору
        from lead_listener.message_handler import MessageHandler
        handler = MessageHandler(notifier=self.notifier)

        try:
            ## search_global доступен через iter_messages с entity=None
            async for message in self.client.iter_messages(
                entity=None,  ## None = search_global
                search=query_text,
                limit=MAX_RESULTS_PER_QUERY,
            ):
                if not message.text:
                    continue

                found += 1

                ## Сохраняем результат (с дедупликацией)
                async with get_session() as session:
                    result = await create_search_global_result(
                        session=session,
                        query_id=query_id or 0,
                        chat_tg_id=message.chat_id or 0,
                        message_id=message.id,
                        message_text=message.text[:2000],
                        author_id=message.sender_id,
                    )
                    await session.commit()

                    if result is None:
                        ## Дубликат — пропускаем
                        continue

                ## Классификация через AI
                try:
                    classification = await self.classifier.classify_message(
                        message.text, query_text
                    )

                    if not classification.is_order or classification.relevance < settings.search_classification_threshold:
                        continue

                    ## Убеждаемся что чат есть в БД (для FK в лиде)
                    chat_id = message.chat_id or 0
                    await self._ensure_chat_in_db(chat_id)

                    ## Подгружаем sender (для global search может быть не загружен)
                    sender = None
                    try:
                        sender = await message.get_sender()
                    except Exception:
                        pass

                    await handler._create_lead_from_message_internal(
                        message=message,
                        chat_id=chat_id,
                        account_id=self.account_id,
                        sender=sender,
                        classification=classification,
                        source="search_global",
                    )
                    leads_created += 1

                except Exception as e:
                    logger.warning(f"⏭️ Ошибка классификации/создания лида: {e}")

        except Exception as e:
            logger.error(f"❌ Ошибка search_global для '{query_text}': {e}")
            raise

        ## Обновляем статистику запроса
        if query_id:
            async with get_session() as session:
                await update_search_query_usage(session, query_id, found)
                await session.commit()

        return found, leads_created
