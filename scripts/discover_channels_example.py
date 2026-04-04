#!/usr/bin/env python3
"""
## Пример скрипта для тестирования автопоиска каналов
Запускает поиск каналов через Telegram Search и сохраняет результаты в БД.

Использование:
    python scripts/discover_channels_example.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from config import settings
from shared.channel_discovery import ChannelDiscoveryService, TelegramSearchProvider
from shared.database.engine import get_session
from shared.utils.logging import setup_logging

# Настройка логирования
logger = setup_logging(__name__)


async def main():
    """Основная функция запуска автопоиска"""
    
    logger.info("=" * 60)
    logger.info("🚀 Запуск тестового автопоиска каналов")
    logger.info("=" * 60)
    
    # Инициализация Telethon клиента
    # Используем отдельную сессию для тестирования
    client = TelegramClient(
        str(settings.sessions_dir / 'discovery_test'),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )
    
    logger.info("📱 Подключение к Telegram...")
    await client.start()
    
    try:
        # Проверка авторизации
        me = await client.get_me()
        logger.info(f"✅ Авторизован как: {me.first_name} (@{me.username or 'no username'})")
        
        # Создание провайдера
        telegram_provider = TelegramSearchProvider(client)
        
        # Получение сессии БД
        async with get_session() as session:
            # Создание сервиса
            service = ChannelDiscoveryService(
                telegram_provider=telegram_provider,
                db_session=session
            )
            
            # Показываем текущую статистику
            stats_before = await service.get_statistics()
            logger.info(f"\n📊 Статистика ДО поиска:")
            logger.info(f"   Всего кандидатов: {stats_before['total']}")
            logger.info(f"   Ожидают проверки: {stats_before['pending']}")
            logger.info(f"   Добавлено в мониторинг: {stats_before['added']}")
            logger.info(f"   Отклонено: {stats_before['rejected']}")
            
            # Тестовые запросы (можно изменить)
            test_queries = [
                "телеграм боты python",
                "фриланс разработка",
                "крипто боты"
            ]
            
            logger.info(f"\n🔍 Поисковые запросы:")
            for i, query in enumerate(test_queries, 1):
                logger.info(f"   {i}. {query}")
            
            # Запуск автопоиска
            logger.info(f"\n🚀 Начинаю поиск с AI-оценкой...")
            logger.info(f"   Лимит на запрос: 10 каналов")
            logger.info(f"   Количество постов для сбора: {settings.channel_posts_count}")
            logger.info(f"   Минимальный порог AI score: {settings.channel_min_score_threshold}")
            
            candidate_ids = await service.discover_channels(
                custom_queries=test_queries,
                limit_per_query=10,
                evaluate_with_ai=True  # Включаем AI-оценку (Фаза 7.2)
            )
            
            # Статистика после
            stats_after = await service.get_statistics()
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ АВТОПОИСК ЗАВЕРШЁН")
            logger.info("=" * 60)
            logger.info(f"📝 Найдено и сохранено новых кандидатов: {len(candidate_ids)}")
            logger.info(f"\n📊 Статистика ПОСЛЕ поиска:")
            logger.info(f"   Всего кандидатов: {stats_after['total']} (было {stats_before['total']})")
            logger.info(f"   Ожидают проверки: {stats_after['pending']}")
            logger.info(f"   Добавлено в мониторинг: {stats_after['added']}")
            logger.info(f"   Отклонено: {stats_after['rejected']}")
            
            # Показываем несколько найденных кандидатов с AI-оценкой
            if candidate_ids:
                logger.info(f"\n📋 Примеры найденных каналов с AI-оценкой:")
                from shared.database import crud
                
                for i, cid in enumerate(candidate_ids[:5], 1):
                    candidate = await crud.get_channel_candidate_by_id(session, cid)
                    if candidate:
                        logger.info(f"\n   {i}. {candidate.title}")
                        logger.info(f"      Username: @{candidate.username or 'нет'}")
                        logger.info(f"      Подписчики: {candidate.members_count or 'неизвестно'}")
                        logger.info(f"      Поисковый запрос: {candidate.search_query}")
                        logger.info(f"      Постов собрано: {len(eval(candidate.recent_posts or '[]'))}")
                        
                        # AI-оценка (Фаза 7.2)
                        if candidate.ai_score is not None:
                            logger.info(f"      🤖 AI Score: {candidate.ai_score}/10")
                            logger.info(f"      📝 Тип контента: {candidate.ai_order_type or 'не определён'}")
                            logger.info(f"      💬 Комментарий: {candidate.ai_comment or 'нет'}")
                        else:
                            logger.info(f"      ⏳ AI-оценка: ещё не проведена")
                
                if len(candidate_ids) > 5:
                    logger.info(f"\n   ... и ещё {len(candidate_ids) - 5} каналов")
                
                # Показываем топ-рейтинг по AI score
                logger.info(f"\n🏆 ТОП-3 канала по AI-оценке:")
                top_candidates = await service.get_top_rated_candidates(min_score=0, limit=3)
                for i, candidate in enumerate(top_candidates, 1):
                    score_emoji = "🔥" if candidate.ai_score >= 8 else "✅" if candidate.ai_score >= 6 else "⚠️"
                    logger.info(
                        f"   {i}. {score_emoji} {candidate.title} "
                        f"(score: {candidate.ai_score}/10, type: {candidate.ai_order_type})"
                    )
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ Тестирование завершено успешно!")
            logger.info("=" * 60)
    
    except Exception as e:
        logger.error(f"\n❌ ОШИБКА: {e}", exc_info=True)
        return 1
    
    finally:
        logger.info("\n🔌 Отключение от Telegram...")
        await client.disconnect()
        logger.info("✅ Отключено")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Прервано пользователем")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

