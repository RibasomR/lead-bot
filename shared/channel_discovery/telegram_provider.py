"""
## Провайдер поиска каналов через Telegram API (Telethon)
Основной источник данных для автопоиска каналов.
Использует существующие userbot клиенты для поиска каналов.
"""

import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telethon.tl.functions.contacts import SearchRequest
from telethon.errors import FloodWaitError

from config import settings

logger = logging.getLogger(__name__)


## Структура данных кандидата канала
class ChannelData:
    """Структура данных о найденном канале"""
    
    def __init__(
        self,
        title: str,
        username: Optional[str] = None,
        tg_chat_id: Optional[int] = None,
        description: Optional[str] = None,
        members_count: Optional[int] = None,
        invite_link: Optional[str] = None,
        recent_posts: Optional[List[Dict[str, Any]]] = None,
        search_query: Optional[str] = None
    ):
        self.title = title
        self.username = username
        self.tg_chat_id = tg_chat_id
        self.description = description
        self.members_count = members_count
        self.invite_link = invite_link
        self.recent_posts = recent_posts or []
        self.search_query = search_query
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            "title": self.title,
            "username": self.username,
            "tg_chat_id": self.tg_chat_id,
            "description": self.description,
            "members_count": self.members_count,
            "invite_link": self.invite_link,
            "recent_posts": json.dumps(self.recent_posts, ensure_ascii=False) if self.recent_posts else None,
            "search_query": self.search_query
        }


## Провайдер поиска через Telegram
class TelegramSearchProvider:
    """
    Провайдер поиска каналов через Telegram API.
    Использует Telethon для глобального поиска каналов по ключевым словам.
    """
    
    def __init__(self, client: TelegramClient):
        """
        Инициализация провайдера
        
        Args:
            client: Авторизованный Telethon клиент
        """
        self.client = client
        self.posts_count = settings.channel_posts_count
    
    async def search_channels(
        self,
        query: str,
        limit: int = 20
    ) -> List[ChannelData]:
        """
        ## Поиск каналов по ключевому слову через Telegram Search
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных каналов с данными
        """
        try:
            logger.info(f"🔍 Начинаю поиск каналов по запросу: '{query}'")
            
            results = []
            
            # Глобальный поиск через Telegram API
            search_result = await self.client(SearchRequest(
                q=query,
                limit=limit
            ))
            
            logger.info(f"📊 Telegram вернул {len(search_result.results)} результатов для '{query}'")
            
            # Обрабатываем результаты
            for result in search_result.results:
                peer = result
                
                # Получаем полную информацию о чате/канале
                try:
                    entity = await self.client.get_entity(peer)
                    
                    # Фильтруем только каналы и супергруппы
                    if not isinstance(entity, (Channel, Chat)):
                        continue
                    
                    # Пропускаем приватные чаты
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        continue
                    
                    ## Фильтр 1: Размер группы (100-30000 участников)
                    if hasattr(entity, 'participants_count') and entity.participants_count:
                        count = entity.participants_count
                        if count < 100:
                            logger.debug(f"⏭️ Пропущен '{entity.title}': слишком мало участников ({count})")
                            continue
                        if count > 30000:
                            logger.debug(f"⏭️ Пропущен '{entity.title}': слишком большой канал ({count})")
                            continue
                    
                    channel_data = await self._extract_channel_data(entity, query)
                    if channel_data:
                        ## Фильтр 2: Анализ постов на наличие заказов
                        has_orders = await self._check_posts_for_orders(channel_data.recent_posts)
                        if not has_orders:
                            logger.debug(f"⏭️ Пропущен '{channel_data.title}': нет признаков заказов в постах")
                            continue
                        
                        results.append(channel_data)
                        logger.debug(f"✅ Добавлен канал: {channel_data.title} (@{channel_data.username})")
                
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить данные об entity: {e}")
                    continue
            
            logger.info(f"✅ Найдено {len(results)} релевантных каналов по запросу '{query}'")
            return results
        
        except FloodWaitError as e:
            logger.error(f"❌ FloodWait: нужно подождать {e.seconds} секунд перед следующим запросом")
            raise
        
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске каналов: {e}", exc_info=True)
            return []
    
    async def _extract_channel_data(
        self,
        entity: Any,
        search_query: str
    ) -> Optional[ChannelData]:
        """
        ## Извлечение данных о канале
        
        Args:
            entity: Telegram entity (Channel/Chat)
            search_query: Исходный поисковый запрос
            
        Returns:
            Объект ChannelData или None
        """
        try:
            # Базовая информация
            title = getattr(entity, 'title', 'Без названия')
            username = getattr(entity, 'username', None)
            tg_chat_id = getattr(entity, 'id', None)
            
            # Описание (about)
            description = None
            try:
                full_entity = await self.client.get_entity(entity)
                if hasattr(full_entity, 'about'):
                    description = full_entity.about
            except Exception as e:
                logger.debug(f"Не удалось получить описание канала: {e}")
            
            # Количество подписчиков
            members_count = None
            if hasattr(entity, 'participants_count'):
                members_count = entity.participants_count
            
            # Формируем ссылку
            invite_link = None
            if username:
                invite_link = f"https://t.me/{username}"
            
            # Получаем последние N постов
            recent_posts = await self._fetch_recent_posts(entity)
            
            return ChannelData(
                title=title,
                username=username,
                tg_chat_id=tg_chat_id,
                description=description,
                members_count=members_count,
                invite_link=invite_link,
                recent_posts=recent_posts,
                search_query=search_query
            )
        
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных канала: {e}")
            return None
    
    async def _fetch_recent_posts(self, entity: Any) -> List[Dict[str, Any]]:
        """
        ## Получение последних N постов из канала
        
        Args:
            entity: Telegram entity (Channel)
            
        Returns:
            Список постов в виде словарей
        """
        posts = []
        
        try:
            # Получаем последние N сообщений
            async for message in self.client.iter_messages(
                entity,
                limit=self.posts_count
            ):
                if message.text:
                    post_data = {
                        "text": message.text[:500],  # Обрезаем до 500 символов
                        "date": message.date.isoformat() if message.date else None,
                        "views": message.views if hasattr(message, 'views') else None
                    }
                    posts.append(post_data)
            
            logger.debug(f"📝 Получено {len(posts)} постов из канала")
        
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить посты канала: {e}")
        
        return posts
    
    async def _check_posts_for_orders(self, posts: List[Dict[str, Any]]) -> bool:
        """
        ## Проверка постов на наличие признаков заказов (Фильтр 2)
        
        Анализирует последние посты канала на наличие ключевых слов,
        указывающих на публикацию заказов, а не просто новостей/обучения.
        
        Args:
            posts: Список постов из канала
            
        Returns:
            True если найдены признаки заказов, False иначе
        """
        if not posts:
            return False
        
        # Ключевые слова, указывающие на заказы
        order_keywords = [
            # Русские
            "нужен", "ищу", "требуется", "заказ", "ищем", 
            "срочно нужен", "оплата", "бюджет", "цена",
            "проект", "разработать", "сделать", "создать",
            "hire", "looking for", "need", "project", "budget",
            "seeking", "payment", "freelance", "remote",
            # Контактная информация
            "@", "telegram", "связаться", "писать", "contact"
        ]
        
        # Слова-исключения (указывают на НЕ заказы)
        exclude_keywords = [
            "вакансия", "vacancy", "в офис", "в штат", 
            "курс", "обучение", "урок", "вебинар",
            "новость", "статья", "анонс"
        ]
        
        matches_count = 0
        exclude_count = 0
        
        for post in posts[:10]:  # Проверяем до 10 последних постов
            text = post.get("text", "").lower()
            
            if not text or len(text) < 50:  # Слишком короткий пост
                continue
            
            # Считаем совпадения
            for keyword in order_keywords:
                if keyword in text:
                    matches_count += 1
            
            # Считаем исключения
            for exclude_word in exclude_keywords:
                if exclude_word in text:
                    exclude_count += 1
        
        # Логика принятия решения
        if matches_count >= 3 and exclude_count < matches_count:
            logger.debug(f"✅ Найдено {matches_count} признаков заказов (исключений: {exclude_count})")
            return True
        else:
            logger.debug(f"❌ Недостаточно признаков заказов: {matches_count} (исключений: {exclude_count})")
            return False
    
    async def search_multiple_queries(
        self,
        queries: List[str],
        limit_per_query: int = 10
    ) -> List[ChannelData]:
        """
        ## Поиск каналов по нескольким запросам
        
        Args:
            queries: Список поисковых запросов
            limit_per_query: Лимит результатов на один запрос
            
        Returns:
            Объединённый список уникальных каналов
        """
        all_channels = []
        seen_usernames = set()
        seen_ids = set()
        
        for query in queries:
            try:
                channels = await self.search_channels(query, limit=limit_per_query)
                
                # Дедупликация по username и tg_chat_id
                for channel in channels:
                    is_unique = True
                    
                    if channel.username and channel.username in seen_usernames:
                        is_unique = False
                    
                    if channel.tg_chat_id and channel.tg_chat_id in seen_ids:
                        is_unique = False
                    
                    if is_unique:
                        all_channels.append(channel)
                        if channel.username:
                            seen_usernames.add(channel.username)
                        if channel.tg_chat_id:
                            seen_ids.add(channel.tg_chat_id)
                
                # Небольшая задержка между запросами во избежание FloodWait
                import asyncio
                await asyncio.sleep(2)
            
            except FloodWaitError as e:
                logger.warning(f"⏳ FloodWait для '{query}': ждём {e.seconds}с")
                import asyncio
                await asyncio.sleep(e.seconds)
            
            except Exception as e:
                logger.error(f"❌ Ошибка поиска по запросу '{query}': {e}")
                continue
        
        logger.info(f"🎯 Всего найдено уникальных каналов: {len(all_channels)}")
        return all_channels

