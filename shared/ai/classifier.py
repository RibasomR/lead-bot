"""
## AI-классификатор заказов (DeepSeek v3.2 через OpenRouter)
Заменяет keyword-фильтрацию на AI-классификацию сообщений.
Использует asyncio.Queue для контроля rate limit и бюджета.
"""

import asyncio
import itertools
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


## Результат классификации сообщения
@dataclass
class ClassificationResult:
    """Результат AI-классификации сообщения из чата"""
    is_order: bool
    relevance: float  # 1-10
    estimated_budget: Optional[str] = None
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    raw_response: Optional[str] = None
    model_used: str = ""


## Промпт для классификатора
CLASSIFIER_PROMPT = """Ты строгий AI-классификатор заказов на IT-разработку. Твоя задача — найти РЕАЛЬНЫЕ заказы, где человек ИЩЕТ исполнителя. Будь скептичен: лучше пропустить сомнительный лид, чем засорить оператора ложными.

## Чат: {chat_title}

## Сообщение:
{message_text}

## Это ЗАКАЗ (is_order=true) ТОЛЬКО если:
- Автор ЯВНО ищет исполнителя: "нужен разработчик", "кто может сделать", "ищу фрилансера", "напишите в ЛС"
- Есть конкретная задача И призыв к действию (написать, откликнуться, взять в работу)
- Описание проекта с намерением нанять/заказать
- Посредник ищет исполнителя для клиента: "кто работал с X? есть клиент", "есть заказчик, нужен кто-то на..."
- Платная консультация: "кто разбирается в X? готов заплатить", "нужна консультация, оплачу"
- Непрямые формулировки с подразумеваемым поиском: "есть задача по...", "есть проект", "кто возьмётся", "кто сможет помочь за оплату"

## Это НЕ заказ (is_order=false):
- Человек РАССКАЗЫВАЕТ что он делал/сделал ("я написал", "реверсил", "настроил") — это опыт, не заказ
- Человек СОВЕТУЕТ как решить задачу ("нужно через X настроить", "попробуй Y") — это совет, не заказ
- Обсуждение технологий, архитектуры, подходов без запроса на исполнителя
- Вопросы по коду ("как сделать X?", "почему не работает Y?") — это помощь, не заказ
- Общение, мемы, флуд, новости, статьи
- Вакансии в штат (офис, полный день, HR)
- Реклама курсов/вебинаров/обучения
- Предложение СВОИХ услуг (человек ищет клиентов, а не исполнителя)

## СПАМ и МУСОР (is_order=false, relevance=1, ВСЕГДА):
- "нужен тезер", "нужен тизер" — это про криптовалюту USDT (тизер = тетер), НЕ заказ на разработку
- "Новый проект! Ищу людей в команду", "пиши @maariaa", "Вся деятельность онлайн" — сетевой маркетинг, скам
- "7000 в день", "3000 в конце дня", "Опыт не нужен", "Можно начать сразу" — скам-вакансии
- Продажа подписок, аккаунтов, ChatGPT Plus — торговля, не заказ
- "купишь у нас", "тестеры для шопа" — торговля
- Одно и то же сообщение от одного автора в разных чатах — спам

## Ключевой тест:
Спроси себя: "Автор этого сообщения (или его клиент/заказчик) ПРЯМО СЕЙЧАС ищет человека, который выполнит работу за деньги?"
Учитывай: автор может искать не для себя, а для клиента. Готовность платить за консультацию тоже считается.
Если ответ не однозначное "да" → is_order=false.

## Наш профиль:
Telegram боты (aiogram, Telethon), веб (Next.js, React), Python-бэкенд, автоматизация (n8n, API), AI-интеграции, крипта/трейдинг боты

## Задача:
Верни СТРОГО JSON:
{{
    "is_order": true/false,
    "relevance": <1-10>,
    "estimated_budget": "<оценка бюджета в рублях или null>",
    "summary": "<суть заказа в 5-10 словах>",
    "tags": ["тег1", "тег2"]
}}

Критерии relevance (только при is_order=true):
- 9-10: Прямой заказ в нашей нише, чёткое ТЗ, автор ждёт откликов
- 7-8: Заказ есть, но в смежной нише или нужны уточнения
- 5-6: Похоже на заказ, но неясная формулировка
- 1-4: Если ставишь такую оценку — скорее всего is_order=false

Ответ ТОЛЬКО валидный JSON, без markdown."""


## AI-классификатор с очередью и rate limiting
class LeadClassifier:
    """
    Классифицирует сообщения через DeepSeek на OpenRouter.
    Использует asyncio.Queue для контроля частоты запросов.
    """

    def __init__(self):
        self._model = settings.deepseek_model
        self._timeout = settings.ai_request_timeout

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._worker_task: Optional[asyncio.Task] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._request_counter = itertools.count()

        ## Общие заголовки для всех запросов
        self._headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/leadhunter",
            "X-Title": "LeadHunter Classifier"
        }

    async def _ensure_worker(self):
        """Запустить воркер если не запущен"""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())
            logger.info(f"🤖 Классификатор запущен: модель={self._model}")

    async def stop(self):
        """Остановить воркер"""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Классификатор остановлен")

    async def classify_message(
        self, text: str, chat_title: str = ""
    ) -> ClassificationResult:
        """
        Классифицировать сообщение через очередь.

        Args:
            text: Текст сообщения
            chat_title: Название чата для контекста

        Returns:
            ClassificationResult с результатом классификации
        """
        await self._ensure_worker()

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        request_id = str(next(self._request_counter))
        self._pending[request_id] = future

        await self._queue.put((request_id, text, chat_title))

        ## Caller ждёт достаточно для всех ретраев воркера
        caller_timeout = self._timeout * 3 + 45

        try:
            result = await asyncio.wait_for(
                future, timeout=caller_timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("⏰ Таймаут классификации (caller)")
            return self._default_result()
        finally:
            self._pending.pop(request_id, None)

    def _drain_stale_items(self) -> int:
        """Очистить протухшие запросы из очереди (caller уже получил таймаут)."""
        drained = 0
        fresh_items = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                req_id = item[0]
                future = self._pending.get(req_id)
                if future is None or future.done():
                    self._queue.task_done()
                    self._pending.pop(req_id, None)
                    drained += 1
                else:
                    fresh_items.append(item)
            except asyncio.QueueEmpty:
                break
        for item in fresh_items:
            self._queue.put_nowait(item)
        if drained > 0:
            logger.info(f"🧹 Очищено {drained} протухших запросов из очереди")
        return drained

    async def _worker(self):
        """Воркер: обрабатывает очередь с задержкой между запросами"""
        logger.debug("🔄 Воркер классификатора запущен")
        consecutive_errors = 0

        while True:
            try:
                request_id, text, chat_title = await self._queue.get()

                ## Пропускаем протухшие запросы (caller уже получил таймаут)
                future = self._pending.get(request_id)
                if future is None or future.done():
                    self._queue.task_done()
                    self._pending.pop(request_id, None)
                    continue

                ## Таймаут воркера: per-request timeout × 3 ретрая + запас на backoff
                worker_timeout = self._timeout * 3 + 30

                try:
                    result = await asyncio.wait_for(
                        self._classify_internal(text, chat_title),
                        timeout=worker_timeout
                    )
                    consecutive_errors = 0
                except asyncio.TimeoutError:
                    logger.error(f"⏰ Воркер: таймаут classify_internal ({worker_timeout}с)")
                    consecutive_errors += 1
                    result = self._default_result()
                except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.PoolTimeout) as e:
                    logger.error(f"❌ Ошибка соединения: {e}")
                    consecutive_errors += 1
                    result = self._default_result()
                except httpx.HTTPStatusError as e:
                    logger.error(f"❌ HTTP ошибка классификации: {e.response.status_code}")
                    consecutive_errors += 1
                    result = self._default_result()
                except Exception as e:
                    logger.error(f"❌ Ошибка классификации: {e}")
                    consecutive_errors += 1
                    result = self._default_result()

                ## Отдаём результат вызывающему коду
                future = self._pending.get(request_id)
                if future and not future.done():
                    future.set_result(result)

                self._queue.task_done()

                ## Backoff при повторных ошибках — не спамим мёртвый API
                if consecutive_errors > 0:
                    backoff = min(30, 2 ** consecutive_errors)
                    logger.warning(f"⏳ Backoff {backoff}с после {consecutive_errors} ошибок подряд")
                    ## При множественных ошибках — чистим протухшие из очереди
                    if consecutive_errors >= 3:
                        self._drain_stale_items()
                    await asyncio.sleep(backoff)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"❌ Критическая ошибка воркера классификатора: {e}")
                await asyncio.sleep(2)

    async def _classify_internal(
        self, text: str, chat_title: str
    ) -> ClassificationResult:
        """
        Выполнить классификацию одного сообщения.
        Создаёт свежий httpx-клиент на каждый запрос — исключает corrupted state.

        Args:
            text: Текст сообщения (обрезается до 2000 символов)
            chat_title: Название чата

        Returns:
            ClassificationResult
        """
        prompt = CLASSIFIER_PROMPT.format(
            chat_title=chat_title or "Неизвестный чат",
            message_text=text[:2000]
        )

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 256
        }

        logger.debug(f"📤 Классификация → {self._model}")

        ## Запрос с retry на 429/500/ошибки соединения
        ## Свежий клиент на каждый запрос — нет corrupted state после сбоев
        response = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    base_url="https://openrouter.ai/api/v1",
                    timeout=httpx.Timeout(self._timeout),
                    headers=self._headers
                ) as client:
                    response = await client.post("/chat/completions", json=payload)
                    response.raise_for_status()
                    break
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503) and attempt < 2:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"⏳ HTTP {e.response.status_code}, ожидание {wait}с (попытка {attempt + 1}/3)")
                    await asyncio.sleep(wait)
                    continue
                raise
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.PoolTimeout, httpx.TimeoutException) as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"⏳ Ошибка соединения, ожидание {wait}с (попытка {attempt + 1}/3): {e}")
                    await asyncio.sleep(wait)
                    continue
                raise

        ## Все попытки провалились — response остался None
        if response is None:
            logger.error("❌ Все 3 попытки запроса провалились, response=None")
            return self._default_result()

        data = response.json()

        ## Защита от неожиданной структуры JSON
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"❌ Неожиданная структура ответа API: {e}\nData: {str(data)[:300]}")
            return self._default_result()

        result = self._parse_response(content)
        result.model_used = self._model
        result.raw_response = content

        logger.info(
            f"📊 Классификация: is_order={result.is_order}, "
            f"relevance={result.relevance}, tags={result.tags}"
        )

        return result

    def _parse_response(self, text: str) -> ClassificationResult:
        """
        Парсинг JSON-ответа от AI.

        Args:
            text: Сырой текст ответа

        Returns:
            ClassificationResult (дефолтный при ошибке парсинга)
        """
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}\nТекст: {text[:300]}")
            return self._default_result()

        ## Валидация и нормализация relevance (может быть null при is_order=false)
        relevance_raw = data.get("relevance")
        try:
            relevance = float(relevance_raw) if relevance_raw is not None else 1.0
        except (ValueError, TypeError):
            logger.warning(f"⚠️ Невалидное значение relevance: {relevance_raw!r}, используем 1.0")
            relevance = 1.0
        relevance = max(1.0, min(10.0, relevance))

        return ClassificationResult(
            is_order=bool(data.get("is_order", False)),
            relevance=relevance,
            estimated_budget=data.get("estimated_budget"),
            summary=data.get("summary", ""),
            tags=data.get("tags", [])
        )

    def _default_result(self) -> ClassificationResult:
        """Дефолтный результат при ошибках (не заказ)"""
        return ClassificationResult(
            is_order=False,
            relevance=1.0,
            summary="Не удалось классифицировать",
            tags=[]
        )


## Синглтон классификатора
_classifier_instance: Optional[LeadClassifier] = None


def get_classifier() -> LeadClassifier:
    """
    Получить глобальный экземпляр классификатора.

    Returns:
        LeadClassifier (синглтон)
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = LeadClassifier()
    return _classifier_instance


async def cleanup_classifier():
    """Очистка ресурсов при завершении приложения"""
    global _classifier_instance
    if _classifier_instance:
        await _classifier_instance.stop()
        _classifier_instance = None
