"""
## Основной сервис автопоиска каналов
Координирует работу провайдеров Telegram Search и TGStat,
сохраняет результаты в БД.
"""

import asyncio
import json
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from shared.channel_discovery.telegram_provider import TelegramSearchProvider, ChannelData
from shared.channel_discovery.tgstat_provider import TGStatProvider
from shared.database import crud
from shared.database.models import ChannelSource
from shared.ai.ai_advisor import get_ai_advisor

logger = logging.getLogger(__name__)


## Основной сервис поиска каналов
class ChannelDiscoveryService:
    """
    Сервис автопоиска и оценки каналов.
    Координирует работу провайдеров и сохранение в БД.
    """
    
    def __init__(
        self,
        telegram_provider: TelegramSearchProvider,
        db_session: AsyncSession
    ):
        """
        Инициализация сервиса
        
        Args:
            telegram_provider: Провайдер Telegram Search (обязательный)
            db_session: Сессия базы данных
        """
        self.telegram_provider = telegram_provider
        self.tgstat_provider = TGStatProvider()  # Опциональный, проверяет наличие ключа сам
        self.ai_advisor = get_ai_advisor()  ## AI Advisor для оценки каналов (Фаза 7.2)
        self.db_session = db_session
        self.search_keywords = settings.channel_search_keywords_list
    
    async def discover_channels(
        self,
        custom_queries: Optional[List[str]] = None,
        limit_per_query: int = 10,
        evaluate_with_ai: bool = True
    ) -> List[int]:
        """
        ## Основная функция поиска каналов (Фаза 7.1 + 7.2)
        
        Args:
            custom_queries: Кастомные поисковые запросы (если None, используются из конфига)
            limit_per_query: Лимит результатов на один запрос
            evaluate_with_ai: Проводить ли AI-оценку после сохранения
            
        Returns:
            Список ID созданных кандидатов в БД
        """
        queries = custom_queries or self.search_keywords
        
        logger.info(f"🚀 Запуск автопоиска каналов по {len(queries)} запросам")
        
        # 1. Поиск через Telegram
        telegram_channels = await self.telegram_provider.search_multiple_queries(
            queries=queries,
            limit_per_query=limit_per_query
        )
        
        logger.info(f"📊 Telegram Search: найдено {len(telegram_channels)} уникальных каналов")
        
        # 2. Обогащение данными TGStat (опционально)
        if self.tgstat_provider.is_available():
            telegram_channels = await self._enrich_with_tgstat(telegram_channels)
        
        # 3. Сохранение в БД
        saved_ids = await self._save_candidates_to_db(telegram_channels)
        
        # 4. AI-оценка сохранённых каналов (Фаза 7.2)
        if evaluate_with_ai and saved_ids:
            logger.info(f"🤖 Запускаю AI-оценку для {len(saved_ids)} новых каналов...")
            await self.evaluate_candidates(candidate_ids=saved_ids)
        
        logger.info(f"✅ Автопоиск завершён: сохранено {len(saved_ids)} новых кандидатов")
        
        return saved_ids
    
    async def _enrich_with_tgstat(
        self,
        channels: List[ChannelData]
    ) -> List[ChannelData]:
        """
        ## Обогащение данных каналов через TGStat
        
        Args:
            channels: Список каналов от Telegram
            
        Returns:
            Обогащённый список каналов
        """
        logger.info("📈 Начинаю обогащение данных через TGStat...")
        
        enriched_count = 0
        
        for channel in channels:
            if not channel.username:
                continue
            
            try:
                tgstat_data = await self.tgstat_provider.enrich_channel_data(channel.username)
                
                if tgstat_data:
                    # Обновляем данные канала
                    if tgstat_data.get("members_count"):
                        channel.members_count = tgstat_data["members_count"]
                    
                    # Добавляем метрики в description
                    metrics_text = self._format_tgstat_metrics(tgstat_data)
                    if metrics_text:
                        channel.description = f"{channel.description or ''}\n\n{metrics_text}"
                    
                    enriched_count += 1
            
            except Exception as e:
                logger.warning(f"⚠️ Не удалось обогатить данные для @{channel.username}: {e}")
                continue
        
        logger.info(f"✅ Обогащено {enriched_count}/{len(channels)} каналов через TGStat")
        return channels
    
    def _format_tgstat_metrics(self, tgstat_data: dict) -> str:
        """Форматирование метрик TGStat для добавления в описание"""
        metrics = []
        
        if tgstat_data.get("avg_post_reach"):
            metrics.append(f"📊 Охват: {tgstat_data['avg_post_reach']}")
        
        if tgstat_data.get("err"):
            metrics.append(f"📈 ERR: {tgstat_data['err']}%")
        
        if tgstat_data.get("category"):
            metrics.append(f"📁 Категория: {tgstat_data['category']}")
        
        return " | ".join(metrics) if metrics else ""
    
    async def _save_candidates_to_db(
        self,
        channels: List[ChannelData]
    ) -> List[int]:
        """
        ## Сохранение кандидатов в БД
        
        Args:
            channels: Список найденных каналов
            
        Returns:
            Список ID созданных записей
        """
        saved_ids = []
        
        for channel in channels:
            try:
                # Проверяем, существует ли уже такой канал
                existing = None
                
                if channel.username:
                    existing = await crud.get_channel_candidate_by_username(
                        self.db_session,
                        channel.username
                    )
                
                if not existing and channel.tg_chat_id:
                    existing = await crud.get_channel_candidate_by_tg_id(
                        self.db_session,
                        channel.tg_chat_id
                    )
                
                if existing:
                    logger.debug(f"⏭️ Канал @{channel.username} уже существует, пропускаю")
                    continue
                
                # Создаём нового кандидата
                channel_dict = channel.to_dict()
                
                candidate = await crud.create_channel_candidate(
                    session=self.db_session,
                    source=ChannelSource.TELEGRAM.value,
                    **channel_dict
                )
                
                saved_ids.append(candidate.id)
                logger.debug(f"✅ Сохранён кандидат: {candidate.title} (ID: {candidate.id})")
            
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения кандидата {channel.title}: {e}")
                continue
        
        # Коммитим изменения
        await self.db_session.commit()
        
        return saved_ids
    
    async def evaluate_candidates(
        self,
        candidate_ids: Optional[List[int]] = None,
        skip_evaluated: bool = True
    ) -> int:
        """
        ## AI-оценка кандидатов каналов (Фаза 7.2)
        
        Args:
            candidate_ids: Список ID кандидатов для оценки (если None, оцениваются все без оценки)
            skip_evaluated: Пропускать ли уже оценённые каналы
            
        Returns:
            Количество оценённых каналов
        """
        logger.info("🤖 Запуск AI-оценки кандидатов...")
        
        # Получаем кандидатов для оценки
        if candidate_ids:
            # Оцениваем конкретные каналы
            candidates = []
            for cid in candidate_ids:
                candidate = await crud.get_channel_candidate_by_id(self.db_session, cid)
                if candidate:
                    if skip_evaluated and candidate.ai_score is not None:
                        logger.debug(f"⏭️ Канал {candidate.title} уже оценён, пропускаю")
                        continue
                    candidates.append(candidate)
        else:
            # Оцениваем все неоценённые
            all_candidates = await crud.get_all_candidates(self.db_session, limit=1000)
            candidates = [
                c for c in all_candidates 
                if c.ai_score is None or not skip_evaluated
            ]
        
        if not candidates:
            logger.info("ℹ️ Нет кандидатов для оценки")
            return 0
        
        logger.info(f"📋 Будет оценено {len(candidates)} каналов")
        
        evaluated_count = 0
        
        for idx, candidate in enumerate(candidates, start=1):
            try:
                logger.info(f"🔍 Оценка канала {idx}/{len(candidates)}: {candidate.title}")
                
                # Парсим посты из JSON
                recent_posts = []
                if candidate.recent_posts:
                    try:
                        recent_posts = json.loads(candidate.recent_posts)
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️ Не удалось распарсить посты для {candidate.title}")
                
                # Вызываем AI-оценку
                evaluation = await self.ai_advisor.evaluate_channel(
                    title=candidate.title,
                    description=candidate.description,
                    members_count=candidate.members_count,
                    recent_posts=recent_posts
                )
                
                # Сохраняем результат
                await crud.update_candidate_ai_data(
                    session=self.db_session,
                    candidate_id=candidate.id,
                    ai_score=float(evaluation["relevance_score"]),
                    ai_comment=evaluation["comment"],
                    ai_order_type=evaluation["order_type"]
                )
                
                evaluated_count += 1
                logger.info(
                    f"✅ [{evaluated_count}/{len(candidates)}] {candidate.title}: "
                    f"score={evaluation['relevance_score']}, type={evaluation['order_type']}"
                )
                
                ## Задержка между AI-запросами для соблюдения Rate Limit (16 req/min = 3.75s/req)
                # Ждём 1 секунду между оценками (с retry логикой при 429)
                if idx < len(candidates):  # Не ждём после последнего
                    logger.debug(f"⏳ Пауза 1 сек перед следующей оценкой...")
                    await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Ошибка оценки канала {candidate.title}: {e}")
                # Даже при ошибке делаем паузу
                if idx < len(candidates):
                    await asyncio.sleep(1)
                continue
        
        # Коммитим изменения
        await self.db_session.commit()
        
        logger.info(f"🎯 AI-оценка завершена: оценено {evaluated_count}/{len(candidates)} каналов")
        return evaluated_count
    
    async def get_top_rated_candidates(
        self,
        min_score: Optional[float] = None,
        limit: int = 50
    ) -> list:
        """
        ## Получение лучших кандидатов по AI-оценке (Фаза 7.2)
        
        Args:
            min_score: Минимальный AI score (если None, используется из конфига)
            limit: Максимальное количество результатов
            
        Returns:
            Список объектов ChannelCandidate, отсортированных по убыванию score
        """
        if min_score is None:
            min_score = settings.channel_min_score_threshold
        
        candidates = await crud.get_pending_candidates(
            session=self.db_session,
            min_score=min_score,
            limit=limit
        )
        
        # Сортируем по score (уже отсортировано в CRUD, но на всякий случай)
        candidates = sorted(
            candidates,
            key=lambda c: c.ai_score if c.ai_score is not None else 0,
            reverse=True
        )
        
        return candidates
    
    async def get_pending_candidates(
        self,
        min_score: Optional[float] = None,
        limit: int = 50
    ) -> list:
        """
        ## Получение непросмотренных кандидатов
        
        Args:
            min_score: Минимальный AI score (если None, используется из конфига)
            limit: Максимальное количество результатов
            
        Returns:
            Список объектов ChannelCandidate
        """
        if min_score is None:
            min_score = settings.channel_min_score_threshold
        
        candidates = await crud.get_pending_candidates(
            session=self.db_session,
            min_score=min_score,
            limit=limit
        )
        
        return candidates
    
    async def get_statistics(self) -> dict:
        """
        ## Получение статистики по кандидатам
        
        Returns:
            Словарь со статистикой
        """
        stats = await crud.get_candidates_statistics(self.db_session)
        return stats

