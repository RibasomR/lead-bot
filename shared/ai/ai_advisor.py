"""
## AI Advisor для LeadHunter
Модуль интеграции с OpenRouter API для анализа лидов и генерации ответов.
Поддерживает fallback между моделями и кеширование результатов в БД.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from shared.database.models import LeadAIData, Lead, CommunicationStyle
from shared.utils.error_handler import get_error_handler, ErrorType, ErrorSeverity


logger = logging.getLogger(__name__)


## Константы для работы с OpenRouter API
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 2


## Enum для типов запросов к AI
class AITaskType(str, Enum):
    """Типы задач для AI"""
    SUMMARY = "summary"
    SCORE = "score"
    REPLY = "reply"
    CHANNEL_EVALUATION = "channel_evaluation"  ## Оценка каналов для автопоиска (Фаза 7.2)


## Промпты для разных задач AI
PROMPTS = {
    AITaskType.SUMMARY: """Ты опытный менеджер по продажам IT-услуг. Проанализируй сообщение потенциального клиента и создай краткое, информативное резюме.

Сообщение клиента:
{message_text}

Создай краткое резюме (максимум 2-3 предложения), которое:
1. Отражает суть заказа
2. Упоминает ключевые технологии или требования
3. Указывает на срочность или бюджетные ограничения (если есть)

Ответь ТОЛЬКО текстом резюме, без дополнительных пояснений.""",

    AITaskType.SCORE: """Ты опытный менеджер по продажам IT-услуг. Оцени качество этого лида и дай рекомендации.

Сообщение клиента:
{message_text}

Проанализируй и верни СТРОГО в формате JSON:
{{
    "quality_score": <число от 1 до 5>,
    "quality_comment": "<краткий комментарий почему такая оценка>",
    "tone_recommendation": "<один из: polite, friendly, aggressive>",
    "price_min": <минимальная цена в рублях>,
    "price_max": <максимальная цена в рублях>,
    "price_explanation": "<краткое объяснение ценовой вилки>"
}}

Критерии оценки quality_score:
- 5: Конкретный заказ, четкие требования, адекватный бюджет
- 4: Хороший заказ, но нужны уточнения
- 3: Средний лид, возможны трудности
- 2: Размытые требования или низкий бюджет
- 1: Неясный или неадекватный запрос

Рекомендации по тону:
- polite: для официальных/крупных заказов
- friendly: для обычных клиентов
- aggressive: для срочных заказов или когда нужно выделиться

Ответ должен быть ТОЛЬКО валидным JSON, без markdown и пояснений.""",

    AITaskType.REPLY: """Ты опытный менеджер по продажам IT-услуг. Создай {count} варианта ответа на заказ клиента.

Сообщение клиента:
{message_text}

Стиль общения: {style_description}
Ценовая вилка: {price_min}-{price_max} руб.

Требования к ответам:
1. Каждый вариант должен быть уникальным
2. Упомяни релевантный опыт
3. Включи ценовую вилку естественным образом
4. Варианты должны отличаться по агрессивности/мягкости подачи
5. Используй эмодзи для дружелюбности (если стиль не aggressive)
6. Будь конкретным и профессиональным

Верни СТРОГО в формате JSON:
{{
    "variants": [
        {{
            "text": "<текст первого варианта>",
            "description": "<краткое описание подхода>"
        }},
        ...
    ]
}}

Ответ должен быть ТОЛЬКО валидным JSON, без markdown и пояснений.""",

    AITaskType.CHANNEL_EVALUATION: """Ты эксперт по поиску фриланс-заказов в IT. Оцени релевантность Telegram-канала для мониторинга заказов на разработку ботов, веб-приложений, автоматизацию и финтех/крипта проекты.

## Информация о канале

**Название**: {title}
**Описание**: {description}
**Подписчиков**: {members_count}

**Последние посты канала**:
{recent_posts}

## КРИТИЧЕСКИ ВАЖНО

Мы ищем ТОЛЬКО группы/чаты, где:
1. ✅ Регулярно публикуются КОНКРЕТНЫЕ заказы от заказчиков
2. ✅ Можно НАПРЯМУЮ связаться с заказчиком (есть контакты, @username)
3. ✅ Это тематическое IT-сообщество с разделом заказов
4. ❌ НЕ биржи фриланса (Kwork, FL.ru, Freelance.ru и т.п.)
5. ❌ НЕ образовательные/новостные каналы
6. ❌ НЕ вакансии в офис/штат
7. ❌ НЕ курсы/обучение/вебинары

## Задача

Оцени, насколько этот канал подходит для поиска заказов на:
- Telegram/Discord/WhatsApp боты
- Веб-разработку (Next.js, React, Python)
- Автоматизацию и интеграции
- Финтех/крипта проекты
- Парсинг и сбор данных

Проанализируй:
1. Реальный контент последних постов (главный критерий!)
2. Есть ли конкретные заказы с описанием задач?
3. Есть ли контакты заказчиков (@username, Telegram)?
4. Тип аудитории (заказчики публикуют заказы?)
5. Качество заказов (не "сделайте за идею")

Верни СТРОГО в формате JSON:
{{
    "relevance_score": <число от 0 до 10>,
    "comment": "<2-3 предложения: почему такая оценка, что публикуют, стоит ли добавлять>",
    "order_type": "<тип контента: фриланс/вакансии/стажировки/обучение/новости/спам/смешанный>",
    "confidence": "<уровень уверенности: high/medium/low>"
}}

## ЖЁСТКИЕ критерии оценки relevance_score:

- 9-10: ИДЕАЛЬНО! Регулярные конкретные заказы с описанием и контактами. Именно то, что нужно!
- 7-8: ХОРОШО. Есть заказы, но бывает шум или не всегда релевантные темы
- 5-6: СОМНИТЕЛЬНО. Редкие заказы или смешанный контент (новости + заказы)
- 3-4: ПЛОХО. Образование/новости/вакансии в офис. Заказы крайне редки
- 1-2: ОЧЕНЬ ПЛОХО. Биржа фриланса / курсы / реклама / другая тема
- 0: МУСОР. Спам, нерелевантная тема, вредный контент

## Примеры правильной оценки:

"Канал про курсы Python" → score = 2, order_type = "обучение"
"Новости IT индустрии" → score = 3, order_type = "новости"
"Вакансии в офис" → score = 3, order_type = "вакансии"
"Биржа Kwork объявления" → score = 0, order_type = "спам"
"Тематический чат с разделом заказов" → score = 8-9, order_type = "фриланс"

Ставь высокую оценку (7+) ТОЛЬКО если видишь реальные заказы с контактами заказчиков!

Ответ должен быть ТОЛЬКО валидным JSON, без markdown кода и пояснений."""
}


## Описания стилей для промптов
STYLE_DESCRIPTIONS = {
    CommunicationStyle.POLITE: "Вежливый и деловой. Используй официальный тон, обращение на 'Вы', минимум эмодзи.",
    CommunicationStyle.FRIENDLY: "Неформальный и дружеский. Можно на 'ты', используй эмодзи, будь открытым и общительным.",
    CommunicationStyle.AGGRESSIVE: "Уверенный и напористый. Подчеркни срочность, конкурентные преимущества, создай FOMO."
}


## HTTP-клиент для OpenRouter API
class OpenRouterClient:
    """Асинхронный HTTP-клиент для работы с OpenRouter API"""
    
    def __init__(self):
        self.base_url = OPENROUTER_BASE_URL
        self.api_key = settings.openrouter_api_key
        self.timeout = settings.ai_request_timeout
        
        self.primary_model = settings.deepseek_model
        self.secondary_model = settings.deepseek_model
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Ленивая инициализация HTTP-клиента"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/leadhunter",
                    "X-Title": "LeadHunter Bot"
                }
            )
        return self._client
    
    async def close(self):
        """Закрытие HTTP-клиента"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _make_request(
        self, 
        messages: List[Dict[str, str]], 
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        retry_count: int = 0,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        ## Выполнение запроса к OpenRouter API с retry логикой
        
        Args:
            messages: Список сообщений в формате OpenAI
            model: ID модели
            temperature: Температура генерации (0-2)
            max_tokens: Максимальное количество токенов
            retry_count: Текущая попытка (для рекурсии)
            max_retries: Максимум попыток
            
        Returns:
            Ответ от API
            
        Raises:
            httpx.HTTPError: При ошибках HTTP
        """
        client = await self._get_client()
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        logger.debug(f"Отправка запроса к OpenRouter. Модель: {model}, попытка {retry_count + 1}/{max_retries + 1}")
        
        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"Получен ответ от OpenRouter. Tokens: {data.get('usage', {})}")
            
            return data
            
        except httpx.HTTPStatusError as e:
            ## Обработка 429 Rate Limit
            if e.response.status_code == 429 and retry_count < max_retries:
                try:
                    error_data = e.response.json()
                    reset_time = error_data.get("error", {}).get("metadata", {}).get("headers", {}).get("X-RateLimit-Reset")
                    
                    if reset_time:
                        # Время в миллисекундах, конвертируем в секунды
                        wait_seconds = max(1, (int(reset_time) - int(time.time() * 1000)) / 1000)
                        wait_seconds = min(wait_seconds, 65)  # Максимум 65 секунд
                    else:
                        # Экспоненциальная задержка: 2, 4, 8 секунд
                        wait_seconds = 2 ** (retry_count + 1)
                    
                    logger.warning(
                        f"⏳ Rate Limit (429) от OpenRouter. "
                        f"Ожидание {wait_seconds:.1f} сек перед повтором (попытка {retry_count + 1}/{max_retries})"
                    )
                    
                    await asyncio.sleep(wait_seconds)
                    
                    # Рекурсивный повтор
                    return await self._make_request(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        retry_count=retry_count + 1,
                        max_retries=max_retries
                    )
                    
                except (ValueError, KeyError) as parse_error:
                    logger.warning(f"Не удалось распарсить время ожидания: {parse_error}")
                    # Fallback на стандартную задержку
                    await asyncio.sleep(2 ** (retry_count + 1))
                    return await self._make_request(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        retry_count=retry_count + 1,
                        max_retries=max_retries
                    )
            
            logger.error(f"HTTP ошибка от OpenRouter: {e.response.status_code} - {e.response.text}")
            raise
            
        except httpx.RequestError as e:
            logger.error(f"Ошибка соединения с OpenRouter: {e}")
            raise
    
    async def generate_completion(
        self, 
        prompt: str,
        use_primary: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        Генерация completion с автоматическим fallback на вторую модель
        
        Args:
            prompt: Промпт для модели
            use_primary: Использовать primary модель (иначе secondary)
            temperature: Температура генерации
            max_tokens: Максимум токенов
            
        Returns:
            Сгенерированный текст
            
        Raises:
            Exception: Если обе модели недоступны
        """
        model = self.primary_model if use_primary else self.secondary_model
        error_handler = get_error_handler()
        
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = await self._make_request(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response["choices"][0]["message"]["content"]
            return content.strip()
            
        except Exception as e:
            logger.warning(f"Ошибка с моделью {model}: {e}")
            
            # Fallback на вторую модель только если использовали первую
            if use_primary:
                logger.info(f"🔄 Переключение на запасную модель: {self.secondary_model}")
                
                ## Уведомляем о проблеме с primary моделью
                await error_handler.handle_ai_error(
                    error=e,
                    model=model,
                    task="generate_completion",
                    notify=False  # Не спамим, это не критично
                )
                
                return await self.generate_completion(
                    prompt=prompt,
                    use_primary=False,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                logger.error("❌ Обе модели недоступны")
                
                ## Уведомляем о критической ошибке - обе модели не работают
                await error_handler.handle_ai_error(
                    error=e,
                    model=f"{self.primary_model} и {self.secondary_model}",
                    task="generate_completion",
                    notify=True  # Это уже критично
                )
                
                raise


## Главный класс для работы с AI
class AIAdvisor:
    """
    Главный класс для работы с AI-советником.
    Предоставляет функции анализа лидов и генерации ответов с кешированием.
    """
    
    def __init__(self):
        self.client = OpenRouterClient()
    
    async def close(self):
        """Закрытие соединений"""
        await self.client.close()
    
    async def generate_lead_summary(
        self, 
        lead_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        ## Генерация краткого резюме лида
        Оптимизация: используется primary модель с пониженной температурой
        
        Args:
            lead_text: Текст сообщения лида
            metadata: Дополнительные метаданные (опционально)
            
        Returns:
            Краткое резюме лида
        """
        logger.info(f"Генерация резюме для лида. Длина текста: {len(lead_text)}")
        
        prompt = PROMPTS[AITaskType.SUMMARY].format(message_text=lead_text)
        
        try:
            summary = await self.client.generate_completion(
                prompt=prompt,
                use_primary=True,
                temperature=0.3,  ## Оптимизация: снижена для более точного резюме
                max_tokens=200
            )
            
            logger.info("✅ Резюме успешно сгенерировано")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации резюме: {e}")
            return "Не удалось создать резюме лида"
    
    async def score_lead(
        self, 
        lead_text: str,
        language: str = "ru"
    ) -> Dict[str, Any]:
        """
        ## Оценка качества лида и генерация рекомендаций
        Оптимизация: используется secondary модель (Qwen) для JSON-задач,
        так как она лучше справляется со структурированным выводом.
        
        Args:
            lead_text: Текст сообщения лида
            language: Язык сообщения
            
        Returns:
            Словарь с оценкой и рекомендациями
        """
        logger.info(f"Оценка качества лида. Язык: {language}")
        
        prompt = PROMPTS[AITaskType.SCORE].format(message_text=lead_text)
        
        try:
            ## Оптимизация: Secondary модель (Qwen) лучше для JSON-задач
            response_text = await self.client.generate_completion(
                prompt=prompt,
                use_primary=False,
                temperature=0.2,  ## Оптимизация: еще ниже для структурированного вывода
                max_tokens=500
            )
            
            # Парсинг JSON ответа
            result = self._parse_json_response(response_text)
            
            # Валидация структуры
            required_keys = ["quality_score", "quality_comment", "tone_recommendation", "price_min", "price_max"]
            if not all(key in result for key in required_keys):
                raise ValueError("Неполный ответ от AI")
            
            logger.info(f"Лид оценен: score={result['quality_score']}, tone={result['tone_recommendation']}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка оценки лида: {e}")
            # Возврат дефолтных значений
            return {
                "quality_score": 3.0,
                "quality_comment": "Не удалось оценить лид автоматически",
                "tone_recommendation": CommunicationStyle.FRIENDLY.value,
                "price_min": 20000.0,
                "price_max": 80000.0,
                "price_explanation": "Стандартная вилка для IT-проектов"
            }
    
    async def suggest_reply_options(
        self,
        lead_text: str,
        style: CommunicationStyle,
        price_min: float,
        price_max: float,
        variants_count: int = 3
    ) -> List[Dict[str, str]]:
        """
        Генерация вариантов ответов для разных стилей
        
        Args:
            lead_text: Текст сообщения лида
            style: Стиль общения
            price_min: Минимальная цена
            price_max: Максимальная цена
            variants_count: Количество вариантов
            
        Returns:
            Список вариантов ответов
        """
        logger.info(f"Генерация вариантов ответов. Стиль: {style.value}, кол-во: {variants_count}")
        
        style_description = STYLE_DESCRIPTIONS.get(style, STYLE_DESCRIPTIONS[CommunicationStyle.FRIENDLY])
        
        prompt = PROMPTS[AITaskType.REPLY].format(
            count=variants_count,
            message_text=lead_text,
            style_description=style_description,
            price_min=int(price_min),
            price_max=int(price_max)
        )
        
        try:
            ## Оптимизация: Primary модель (Llama) лучше для креативных текстов
            response_text = await self.client.generate_completion(
                prompt=prompt,
                use_primary=True,
                temperature=0.7,  ## Оптимизация: слегка снижена для баланса креатива/качества
                max_tokens=1500
            )
            
            # Парсинг JSON ответа
            result = self._parse_json_response(response_text)
            
            variants = result.get("variants", [])
            
            if not variants:
                raise ValueError("AI не вернул варианты ответов")
            
            logger.info(f"Сгенерировано {len(variants)} вариантов ответов")
            return variants
            
        except Exception as e:
            logger.error(f"Ошибка генерации вариантов ответов: {e}")
            # Возврат заглушки
            return [
                {
                    "text": f"Здравствуйте! Готовы помочь с вашим проектом. Стоимость работ: {int(price_min)}-{int(price_max)} руб. Обсудим детали?",
                    "description": "Стандартный шаблон ответа"
                }
            ]
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        Парсинг JSON из ответа AI (убирает markdown и лишнее)
        
        Args:
            text: Текст ответа от AI
            
        Returns:
            Распарсенный JSON
            
        Raises:
            ValueError: Если не удалось распарсить JSON
        """
        # Убираем markdown форматирование
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}\nТекст: {text[:200]}")
            raise ValueError(f"Не удалось распарсить JSON ответ от AI: {e}")
    
    async def evaluate_channel(
        self,
        title: str,
        description: Optional[str],
        members_count: Optional[int],
        recent_posts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        ## Оценка релевантности канала для мониторинга лидов (Фаза 7.2)
        
        Args:
            title: Название канала
            description: Описание канала
            members_count: Количество подписчиков
            recent_posts: Список последних постов (dict с text, date, views)
            
        Returns:
            Dict с оценкой: relevance_score, comment, order_type, confidence
        """
        logger.info(f"🔍 Начинаю AI-оценку канала: {title}")
        
        # Форматируем посты для промпта
        if recent_posts:
            posts_text = "\n\n".join([
                f"Пост {i+1} (просмотров: {post.get('views', 'н/д')}):\n{post.get('text', '(нет текста)')[:300]}"
                for i, post in enumerate(recent_posts[:10])  # Берём макс 10 постов
            ])
        else:
            posts_text = "(Нет постов для анализа)"
        
        # Формируем промпт
        prompt = PROMPTS[AITaskType.CHANNEL_EVALUATION].format(
            title=title or "Без названия",
            description=description or "Описание отсутствует",
            members_count=members_count if members_count is not None else "неизвестно",
            recent_posts=posts_text
        )
        
        try:
            # Отправляем запрос к AI (используем primary модель - Llama 3.3)
            response_text = await self.client.generate_completion(
                prompt=prompt,
                use_primary=True,  # Llama 3.3 70B для оценки каналов
                max_tokens=1000
            )
            
            # Парсим JSON
            result = self._parse_json_response(response_text)
            
            # Валидация обязательных полей
            required_fields = ["relevance_score", "comment", "order_type", "confidence"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Отсутствует обязательное поле: {field}")
            
            # Валидация score (0-10)
            score = float(result["relevance_score"])
            if not 0 <= score <= 10:
                logger.warning(f"⚠️ AI вернул score вне диапазона: {score}, ограничиваю")
                score = max(0, min(10, score))
                result["relevance_score"] = score
            
            logger.info(f"✅ AI-оценка канала '{title}': score={score}, type={result['order_type']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка AI-оценки канала '{title}': {e}")
            # Возвращаем дефолтную оценку
            return {
                "relevance_score": 0.0,
                "comment": f"Не удалось оценить канал: {str(e)}",
                "order_type": "unknown",
                "confidence": "low"
            }
    
    async def get_or_create_lead_analysis(
        self,
        db: AsyncSession,
        lead: Lead,
        force_refresh: bool = False
    ) -> LeadAIData:
        """
        Получение или создание анализа лида с кешированием.
        v2: генерирует один черновик через ReplyGenerator вместо 3 вариантов.

        Args:
            db: Сессия базы данных
            lead: Объект лида
            force_refresh: Принудительное обновление анализа

        Returns:
            Объект LeadAIData с анализом
        """
        # Проверка кеша
        if not force_refresh and lead.ai_data:
            logger.info(f"Использование кешированного анализа для лида {lead.id}")
            return lead.ai_data

        logger.info(f"Создание нового анализа для лида {lead.id}")

        try:
            # Генерация резюме
            summary = await self.generate_lead_summary(lead.message_text)

            # Оценка лида
            score_data = await self.score_lead(lead.message_text, lead.language)

            ## v2: генерация одного черновика через ReplyGenerator
            from shared.ai.reply_generator import get_reply_generator
            from shared.database.crud import get_freelancer_profile

            reply_generator = get_reply_generator()
            profile = await get_freelancer_profile(db)
            tone = score_data.get("tone_recommendation", "friendly")
            generated_reply = await reply_generator.generate_reply(
                lead_text=lead.message_text,
                style=tone,
                freelancer_profile=profile,
            )

            # Создание или обновление записи в БД
            if lead.ai_data:
                ai_data = lead.ai_data
                ai_data.updated_at = datetime.utcnow()
            else:
                ai_data = LeadAIData(lead_id=lead.id)
                db.add(ai_data)

            # Заполнение данных
            ai_data.summary = summary
            ai_data.quality_score = score_data["quality_score"]
            ai_data.tone_recommendation = score_data["tone_recommendation"]
            ai_data.price_min = score_data["price_min"]
            ai_data.price_max = score_data["price_max"]
            ai_data.generated_reply = generated_reply
            ai_data.ai_model_used = self.client.primary_model
            ai_data.raw_response = json.dumps(score_data, ensure_ascii=False)

            await db.commit()
            await db.refresh(ai_data)

            ## v2: сохраняем черновик в лид
            if generated_reply and not lead.draft_reply:
                lead.draft_reply = generated_reply
                await db.commit()

            logger.info(f"Анализ для лида {lead.id} успешно сохранен")
            return ai_data

        except Exception as e:
            logger.error(f"Ошибка создания анализа лида: {e}")
            await db.rollback()
            raise
    
    async def refresh_reply_variants(
        self,
        db: AsyncSession,
        lead: Lead,
        style: CommunicationStyle
    ) -> List[Dict[str, str]]:
        """
        Обновление вариантов ответов для конкретного стиля
        
        Args:
            db: Сессия базы данных
            lead: Объект лида
            style: Стиль общения
            
        Returns:
            Обновленные варианты ответов
        """
        logger.info(f"Обновление вариантов ответов для лида {lead.id}, стиль: {style.value}")
        
        # Получаем данные анализа
        ai_data = await self.get_or_create_lead_analysis(db, lead, force_refresh=False)
        
        # Генерируем новые варианты
        reply_variants = await self.suggest_reply_options(
            lead_text=lead.message_text,
            style=style,
            price_min=ai_data.price_min or 20000,
            price_max=ai_data.price_max or 80000,
            variants_count=3
        )
        
        # Обновляем в БД
        ai_data.reply_variants = json.dumps(reply_variants, ensure_ascii=False)
        ai_data.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return reply_variants


## Глобальный экземпляр AI Advisor (синглтон)
_ai_advisor_instance: Optional[AIAdvisor] = None


def get_ai_advisor() -> AIAdvisor:
    """
    Получение глобального экземпляра AIAdvisor (синглтон)
    
    Returns:
        Экземпляр AIAdvisor
    """
    global _ai_advisor_instance
    
    if _ai_advisor_instance is None:
        _ai_advisor_instance = AIAdvisor()
    
    return _ai_advisor_instance


async def cleanup_ai_advisor():
    """Очистка ресурсов AI Advisor при завершении приложения"""
    global _ai_advisor_instance
    
    if _ai_advisor_instance is not None:
        await _ai_advisor_instance.close()
        _ai_advisor_instance = None

