"""
## Обработчик входящих сообщений
Обрабатывает новые сообщения из чатов, классифицирует через AI и создаёт лиды в БД.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Optional, Dict, Tuple
from loguru import logger

from telethon.events import NewMessage
from telethon.tl.types import User, Chat as TelegramChat, Channel
from telethon.extensions import html as tg_html

from config import settings
from shared.database.engine import get_session
from shared.database.crud import (
    get_chat_by_tg_id, create_lead, get_lead_by_chat_message,
    get_account_by_id
)
from shared.database.models import Lead, LeadAIData, Chat
from lead_listener.filters import LeadFilter
from shared.ai.ai_advisor import AIAdvisor
from shared.ai.classifier import get_classifier, ClassificationResult


## Очистка markdown-маркеров, дублирующих HTML-теги из Telethon entities
def _clean_message_html(message) -> str:
    """
    Конвертирует entities в HTML и убирает дублирующие markdown-маркеры.
    Telegram-клиенты иногда оставляют ** / __ в тексте при наличии bold/italic entities.
    """
    html_text = tg_html.unparse(message.text, message.entities or [])
    ## Убираем markdown-маркеры, которые дублируют HTML-теги
    html_text = re.sub(r'\*\*', '', html_text)
    html_text = re.sub(r'(?<!\w)__(?!\w)', '', html_text)
    return html_text


## Лог классификации для аналитики (простой JSONL-файл)
CLASSIFICATION_LOG = "/app/logs/classification.jsonl"


def _log_classification(chat_title: str, message_id: int, text: str, result, accepted: bool):
    """Записать решение классификатора в файл для аналитики."""
    try:
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "chat": chat_title,
            "msg_id": message_id,
            "text": text[:300],
            "is_order": result.is_order if result else None,
            "relevance": result.relevance if result else None,
            "tags": result.tags if result else None,
            "accepted": accepted,
        }
        with open(CLASSIFICATION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  ## не ломаем основной поток из-за логов


## Класс для обработки новых сообщений из Telegram
class MessageHandler:
    """
    Обрабатывает входящие сообщения, применяет фильтры и создаёт лиды.
    """
    
    ## TTL для кеша классифицированных сообщений (секунды)
    ## 2 дня — покрывает ретро-обработку с запасом
    CLASSIFICATION_CACHE_TTL = 172800

    def __init__(self, notifier=None):
        self.filter = LeadFilter()
        self.ai_advisor = AIAdvisor()
        self.classifier = get_classifier()
        self.notifier = notifier
        ## Множество для хранения ссылок на фоновые задачи (защита от GC)
        self._background_tasks: set = set()
        ## Кеш классифицированных сообщений: (chat_id, message_id) -> timestamp
        ## Предотвращает повторную AI-классификацию одного сообщения
        self._classified_cache: Dict[Tuple[int, int], float] = {}

    def _create_background_task(self, coro) -> asyncio.Task:
        """
        Создать фоновую задачу с защитой от сборки мусора и логированием ошибок.

        :param coro: Корутина для выполнения
        :return: Созданная задача
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _on_done(t: asyncio.Task):
            self._background_tasks.discard(t)
            if not t.cancelled() and t.exception():
                logger.error(f"❌ Фоновая задача завершилась с ошибкой: {t.exception()}")

        task.add_done_callback(_on_done)
        return task
        
    async def process_message(self, event: NewMessage.Event, account_id: int):
        """
        Обработать новое сообщение из чата (real-time).
        
        Args:
            event: Событие нового сообщения от Telethon
            account_id: ID аккаунта, который получил сообщение
        """
        try:
            message = event.message
            
            logger.debug(f"🔍 Обработка сообщения {message.id} из чата {event.chat_id}")
            
            # Игнорируем сообщения без текста
            if not message.text:
                logger.debug(f"⏭️ Сообщение {message.id} без текста, пропускаю")
                return
                
            # Игнорируем системные сообщения и сервисные
            if message.action:
                logger.debug(f"⏭️ Сообщение {message.id} - системное, пропускаю")
                return
                
            # Игнорируем сообщения от ботов
            sender = await event.get_sender()
            if sender and hasattr(sender, 'bot') and sender.bot:
                logger.debug(f"⏭️ Пропуск сообщения от бота: {sender.id}")
                return
                
            # Делегируем основную обработку
            await self._process_message_internal(
                message=message,
                chat_id=event.chat_id,
                account_id=account_id,
                sender=sender
            )
                
        except Exception as e:
            logger.exception(f"❌ Ошибка обработки сообщения: {e}")
    
    async def process_message_direct(self, message, chat_id: int, account_id: int):
        """
        ## Обработать сообщение напрямую (для ретроспективного парсинга)
        
        Args:
            message: Объект Message от Telethon
            chat_id: ID чата
            account_id: ID аккаунта
        """
        try:
            # Игнорируем сообщения без текста
            if not message.text:
                return
                
            # Игнорируем системные сообщения
            if message.action:
                return
            
            # Получаем отправителя
            sender = message.sender if hasattr(message, 'sender') else None
            
            # Игнорируем ботов
            if sender and hasattr(sender, 'bot') and sender.bot:
                return
            
            # Делегируем основную обработку
            await self._process_message_internal(
                message=message,
                chat_id=chat_id,
                account_id=account_id,
                sender=sender
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка прямой обработки сообщения: {e}")
    
    async def _process_message_internal(self, message, chat_id: int, account_id: int, sender=None):
        """
        ## Внутренняя логика обработки сообщения (общая для real-time и ретроспективной обработки)
        
        Args:
            message: Объект Message от Telethon
            chat_id: ID чата
            account_id: ID аккаунта
            sender: Отправитель сообщения (опционально)
        """
        try:
            # Проверка на дубликаты в БД
            async with get_session() as session:
                chat_db = await get_chat_by_tg_id(session, chat_id)
                
                if not chat_db:
                    logger.warning(f"⚠️ Чат {chat_id} не найден в БД (но получено сообщение!)")
                    return
                    
                logger.debug(f"✅ Чат найден в БД: '{chat_db.title}' (ID: {chat_db.id})")
                
                # Проверяем, не создавали ли мы уже лид для этого сообщения
                existing_lead = await get_lead_by_chat_message(
                    session, 
                    chat_db.id, 
                    message.id
                )
                
                if existing_lead:
                    logger.debug(f"⏭️ Лид для сообщения {message.id} уже существует")
                    return
                    
            ## Дедупликация: проверяем, не классифицировали ли уже это сообщение
            cache_key = (chat_id, message.id)
            now = time.monotonic()
            if cache_key in self._classified_cache:
                logger.debug(f"⏭️ Сообщение {message.id} в чате {chat_id} уже классифицировано, пропуск")
                return

            ## Периодическая очистка устаревших записей кеша (каждые ~1000 записей)
            if len(self._classified_cache) > 1000:
                cutoff = now - self.CLASSIFICATION_CACHE_TTL
                self._classified_cache = {
                    k: v for k, v in self._classified_cache.items() if v > cutoff
                }

            ## AI-классификация сообщения (v2: заменяет keyword-фильтрацию)
            logger.debug(f"🤖 Классификация сообщения {message.id}: {message.text[:50]}...")
            classification = await self.classifier.classify_message(
                message.text, chat_db.title
            )

            ## Запоминаем что сообщение классифицировано (до проверки порога!)
            self._classified_cache[cache_key] = now

            ## Проверяем порог: is_order + relevance >= threshold
            if not classification.is_order or classification.relevance < settings.classification_threshold:
                logger.debug(
                    f"⏭️ Не заказ или низкая релевантность: "
                    f"is_order={classification.is_order}, "
                    f"relevance={classification.relevance}"
                )
                _log_classification(chat_db.title, message.id, message.text, classification, accepted=False)
                return

            logger.info(
                f"🎯 Найден лид в чате {chat_id} (сообщение {message.id}): "
                f"relevance={classification.relevance}, tags={classification.tags}"
            )
            _log_classification(chat_db.title, message.id, message.text, classification, accepted=True)

            ## Создаём лид с данными классификации
            await self._create_lead_from_message_internal(
                message, chat_id, account_id, sender, classification
            )
            
        except Exception as e:
            logger.exception(f"❌ Ошибка обработки сообщения: {e}")
            
    async def _create_lead_from_message(self, event: NewMessage.Event, account_id: int):
        """
        Создать запись лида в БД на основе сообщения (для real-time событий).
        
        Args:
            event: Событие нового сообщения
            account_id: ID аккаунта, который обнаружил лид
        """
        try:
            message = event.message
            sender = await event.get_sender()
            await self._create_lead_from_message_internal(message, event.chat_id, account_id, sender)
        except Exception as e:
            logger.exception(f"❌ Ошибка создания лида: {e}")
    
    async def _create_lead_from_message_internal(
        self, message, chat_id: int, account_id: int,
        sender=None, classification: Optional[ClassificationResult] = None,
        source: str = "monitor"
    ):
        """
        ## Внутренняя логика создания лида (общая для real-time и ретроспективной обработки)

        Args:
            message: Объект Message от Telethon
            chat_id: ID чата в Telegram
            account_id: ID аккаунта, который обнаружил лид
            sender: Отправитель сообщения (опционально)
            classification: Результат AI-классификации (v2)
            source: Источник лида ('monitor' или 'search_global')
        """
        try:
            # Извлекаем информацию об авторе
            author_id = sender.id if sender else None
            author_username = getattr(sender, 'username', None) if sender else None
            author_name = None
            
            if sender and isinstance(sender, User):
                author_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                
            # Формируем ссылку на сообщение
            message_url = self._build_message_url_direct(message, chat_id)
            
            # Определяем язык сообщения
            language = self.filter.detect_language(message.text)
            
            # Извлекаем стек технологий
            stack_tags = self.filter.extract_stack(message.text)
            
            async with get_session() as session:
                # Получаем чат из БД
                chat_db = await get_chat_by_tg_id(session, chat_id)
                
                if not chat_db:
                    logger.error(f"❌ Чат {chat_id} не найден в БД")
                    return
                    
                # Создаём лид
                lead = await create_lead(
                    session=session,
                    chat_id=chat_db.id,
                    message_id=message.id,
                    author_id=author_id,
                    author_username=author_username,
                    author_name=author_name,
                    message_text=_clean_message_html(message),
                    message_url=message_url,
                    language=language,
                    stack_tags=stack_tags,
                    source=source
                )
                
                ## Сохраняем данные AI-классификатора в lead_ai_data (v2)
                if classification:
                    ai_data = LeadAIData(
                        lead_id=lead.id,
                        summary=classification.summary,
                        is_order=classification.is_order,
                        relevance_score=classification.relevance,
                        estimated_budget=classification.estimated_budget,
                        tags=json.dumps(classification.tags, ensure_ascii=False) if classification.tags else None,
                        classifier_model=classification.model_used,
                        raw_response=classification.raw_response
                    )
                    session.add(ai_data)

                await session.commit()

                logger.info(
                    f"✅ Лид #{lead.id} создан для сообщения {message.id} "
                    f"в чате '{chat_db.title}'"
                )

                ## AI-анализ (quality_score, tone, цена) — только если классификатор не заполнил данные
                ## Иначе race condition: классификатор уже создал LeadAIData, а delayed-задача
                ## может не увидеть её до commit и создать дубль → IntegrityError
                if not classification:
                    self._create_background_task(self._analyze_lead_with_ai_delayed(lead.id))

                # Отправляем уведомление в Admin Bot
                if self.notifier:
                    self._create_background_task(self.notifier.notify_new_lead(lead.id))
                
        except Exception as e:
            logger.exception(f"❌ Ошибка создания лида: {e}")
            
    async def _build_message_url(self, event: NewMessage.Event) -> Optional[str]:
        """
        Построить ссылку на сообщение в чате (для real-time событий).
        
        Args:
            event: Событие сообщения
            
        Returns:
            URL или None
        """
        try:
            chat = await event.get_chat()
            message = event.message
            
            # Для каналов и публичных групп
            if hasattr(chat, 'username') and chat.username:
                return f"https://t.me/{chat.username}/{message.id}"
                
            # Для приватных чатов используем chat_id
            # Формат: https://t.me/c/{chat_id без -100}/{message_id}
            if str(event.chat_id).startswith('-100'):
                chat_id_clean = str(event.chat_id)[4:]  # Убираем -100
                return f"https://t.me/c/{chat_id_clean}/{message.id}"
                
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка построения URL сообщения: {e}")
            return None
    
    def _build_message_url_direct(self, message, chat_id: int) -> Optional[str]:
        """
        ## Построить ссылку на сообщение напрямую (для ретроспективного и global search)

        Args:
            message: Объект Message
            chat_id: ID чата

        Returns:
            URL или None
        """
        try:
            ## Пытаемся получить username из peer_id или chat объекта
            chat_username = None
            if hasattr(message, 'peer_id'):
                peer = message.peer_id
                if hasattr(peer, 'username'):
                    chat_username = peer.username

            ## Для Telethon: chat может быть прикреплён к message
            if not chat_username and hasattr(message, 'chat') and message.chat:
                chat_username = getattr(message.chat, 'username', None)

            ## Для публичных чатов с username
            if chat_username:
                return f"https://t.me/{chat_username}/{message.id}"

            ## Для приватных чатов — формат t.me/c/{id}/{msg_id}
            chat_id_str = str(chat_id)
            if chat_id_str.startswith('-100'):
                chat_id_clean = chat_id_str[4:]
                return f"https://t.me/c/{chat_id_clean}/{message.id}"

            ## Для положительных channel_id (Telethon иногда не добавляет -100)
            if chat_id > 0:
                return f"https://t.me/c/{chat_id}/{message.id}"

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка построения URL сообщения: {e}")
            return None
            
    async def _analyze_lead_with_ai_delayed(self, lead_id: int):
        """
        ## Обёртка для AI анализа с задержкой (защита от rate limit)
        
        Args:
            lead_id: ID лида в БД
        """
        import random
        
        # Случайная задержка от 1 до 5 секунд чтобы распределить нагрузку
        delay = random.uniform(1.0, 5.0)
        await asyncio.sleep(delay)
        
        await self._analyze_lead_with_ai(lead_id)
    
    async def _analyze_lead_with_ai(self, lead_id: int):
        """
        Асинхронно проанализировать лид через AI Advisor.
        
        Args:
            lead_id: ID лида в БД
        """
        try:
            logger.info(f"🤖 Запуск AI анализа для лида #{lead_id}...")
            
            async with get_session() as session:
                from shared.database.crud import get_lead_by_id
                
                lead = await get_lead_by_id(session, lead_id)
                
                if not lead:
                    logger.error(f"❌ Лид #{lead_id} не найден")
                    return
                    
                ## Plain text для AI (без HTML-тегов)
                plain_text = re.sub(r'<[^>]+>', '', lead.message_text)

                # Генерация саммари
                summary_data = await self.ai_advisor.generate_lead_summary(
                    plain_text,
                    {
                        'language': lead.language,
                        'stack': lead.stack_tags
                    }
                )

                # Оценка лида
                score_data = await self.ai_advisor.score_lead(plain_text)
                
                # Обработка ответов от AI (могут быть строками или dict)
                if isinstance(summary_data, str):
                    summary = summary_data
                else:
                    summary = summary_data.get('summary', summary_data) if isinstance(summary_data, dict) else str(summary_data)
                
                if isinstance(score_data, str):
                    # Если строка - парсим или используем дефолтные значения
                    quality_score = 3
                    tone_recommendation = 'neutral'
                    price_min = 10000
                    price_max = 50000
                else:
                    quality_score = score_data.get('quality_score', 3)
                    tone_recommendation = score_data.get('tone_recommendation', 'neutral')
                    price_min = score_data.get('price_min', 10000)
                    price_max = score_data.get('price_max', 50000)
                
                # Сохранение результатов в БД
                from shared.database.crud import (
                    create_lead_ai_data, get_lead_ai_data, update_lead_ai_data
                )
                
                # Проверяем, есть ли уже AI данные для этого лида
                existing_ai_data = await get_lead_ai_data(session, lead_id)
                
                if existing_ai_data:
                    # Обновляем существующие данные
                    await update_lead_ai_data(
                        session=session,
                        lead_id=lead_id,
                        summary=summary,
                        quality_score=quality_score,
                        tone_recommendation=tone_recommendation,
                        price_min=price_min,
                        price_max=price_max,
                        ai_model_used=settings.ai_model_primary
                    )
                else:
                    # Создаём новые данные
                    await create_lead_ai_data(
                        session=session,
                        lead_id=lead_id,
                        summary=summary,
                        quality_score=quality_score,
                        tone_recommendation=tone_recommendation,
                        price_min=price_min,
                        price_max=price_max,
                        ai_model_used=settings.ai_model_primary
                    )
                
                await session.commit()
                
                logger.info(f"✅ AI анализ для лида #{lead_id} завершён")
                
        except Exception as e:
            logger.exception(f"❌ Ошибка AI анализа лида #{lead_id}: {e}")

