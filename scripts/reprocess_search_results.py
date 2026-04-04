"""
## Переклассификация результатов глобального поиска
Прогоняет все необработанные search_global_results через AI-классификатор
и создаёт лиды из тех, что определены как заказы.

Запуск: docker compose exec lead_listener python scripts/reprocess_search_results.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from config import settings
from shared.database.engine import get_session, init_db
from shared.database.models import SearchGlobalResult, Lead, LeadAIData, Chat
from shared.database.crud import get_chat_by_tg_id, create_lead, get_lead_by_chat_message
from shared.ai.classifier import get_classifier
from lead_listener.filters import LeadFilter

from sqlalchemy import select, update

## ID чатов-исключений (чат с ботом, личные чаты оператора)
SKIP_CHAT_IDS = {8539947869, 8534939920}


async def main():
    await init_db()
    classifier = get_classifier()
    lead_filter = LeadFilter()

    logger.info("🔄 Загрузка необработанных результатов глобального поиска...")

    async with get_session() as session:
        results = (await session.execute(
            select(SearchGlobalResult)
            .where(SearchGlobalResult.is_processed == False)
            .order_by(SearchGlobalResult.id)
        )).scalars().all()

    total = len(results)
    logger.info(f"📋 Найдено {total} необработанных результатов")

    leads_created = 0
    skipped_bot = 0
    errors = 0

    for i, result in enumerate(results, 1):
        ## Пропускаем сообщения из чата бота и личных чатов
        if result.chat_tg_id in SKIP_CHAT_IDS:
            skipped_bot += 1
            async with get_session() as session:
                await session.execute(
                    update(SearchGlobalResult)
                    .where(SearchGlobalResult.id == result.id)
                    .values(is_processed=True)
                )
                await session.commit()
            continue

        if not result.message_text or len(result.message_text.strip()) < 10:
            async with get_session() as session:
                await session.execute(
                    update(SearchGlobalResult)
                    .where(SearchGlobalResult.id == result.id)
                    .values(is_processed=True)
                )
                await session.commit()
            continue

        try:
            classification = await classifier.classify_message(result.message_text)

            ## Помечаем как обработанное
            async with get_session() as session:
                await session.execute(
                    update(SearchGlobalResult)
                    .where(SearchGlobalResult.id == result.id)
                    .values(is_processed=True)
                )
                await session.commit()

            if not classification.is_order or classification.relevance < settings.search_classification_threshold:
                if i % 20 == 0:
                    logger.info(f"  [{i}/{total}] не заказ, пропуск...")
                continue

            ## Это заказ — создаём лид
            logger.info(f"🎯 [{i}/{total}] ЗАКАЗ найден! relevance={classification.relevance}")
            logger.info(f"   Текст: {result.message_text[:150]}...")

            async with get_session() as session:
                ## Ищем чат в БД по tg_chat_id
                chat_db = await get_chat_by_tg_id(session, result.chat_tg_id)
                if not chat_db:
                    ## Создаём запись чата (supergroup по умолчанию для Telegram-групп)
                    chat_db = Chat(
                        tg_chat_id=result.chat_tg_id,
                        title=f"Chat {result.chat_tg_id}",
                        type="supergroup",
                        enabled=False,
                    )
                    session.add(chat_db)
                    await session.flush()

                ## Проверяем дедупликацию по внутреннему chat_id (FK)
                existing = await get_lead_by_chat_message(
                    session, chat_db.id, result.message_id
                )
                if existing:
                    logger.info(f"   ⏭️ Лид уже существует (#{existing.id}), пропуск")
                    await session.commit()
                    continue

                language = lead_filter.detect_language(result.message_text)
                stack_tags = lead_filter.extract_stack(result.message_text)

                lead = await create_lead(
                    session=session,
                    chat_id=chat_db.id,
                    message_id=result.message_id,
                    author_id=result.author_id,
                    author_username=None,
                    author_name=None,
                    message_text=result.message_text,
                    message_url=None,
                    language=language,
                    stack_tags=stack_tags,
                    source="search_global",
                )

                ## AI-данные
                ai_data = LeadAIData(
                    lead_id=lead.id,
                    summary=classification.summary,
                    is_order=classification.is_order,
                    relevance_score=classification.relevance,
                    estimated_budget=classification.estimated_budget,
                    tags=json.dumps(classification.tags, ensure_ascii=False) if classification.tags else None,
                    classifier_model=classification.model_used,
                    raw_response=classification.raw_response,
                )
                session.add(ai_data)
                await session.commit()

                leads_created += 1
                logger.info(f"   ✅ Лид #{lead.id} создан!")

        except Exception as e:
            errors += 1
            logger.error(f"   ❌ [{i}/{total}] Ошибка: {e}")

        ## Задержка между запросами к AI
        await asyncio.sleep(0.5)

    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"✅ Готово!")
    logger.info(f"   Обработано: {total}")
    logger.info(f"   Пропущено (чат бота): {skipped_bot}")
    logger.info(f"   Лидов создано: {leads_created}")
    logger.info(f"   Ошибок: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
