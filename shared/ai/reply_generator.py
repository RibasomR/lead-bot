"""
## Генератор автоответов через Gemini (Antigravity Proxy)
Один качественный черновик вместо 3 вариантов.
Fallback на DeepSeek через OpenRouter если proxy недоступен.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


## Промпт для генерации автоответа
REPLY_PROMPT = """Ты пишешь ответ от имени фрилансера на заказ из Telegram-чата.
Контекст: это сообщение отправляется человеку в личные сообщения. Вы уже в ЛС, не нужно просить "напиши в личку/ЛС".

## Сообщение заказчика:
{lead_text}

## Профиль фрилансера:
{profile_section}

## Тон:
Спокойный, профессиональный, но живой. Пиши как нормальный человек в телеграме, а не как робот.
Обращение на "вы" с маленькой буквы. Без канцелярита и пафоса.

## Структура ответа:
1. Привязка — человек должен понять зачем ты пишешь ("Привет! Ты писал в чате про автоматизацию ТГ-каналов — я как раз этим занимаюсь")
2. Кратко кто ты ("Делаю ботов и автоматизацию на Python + n8n")
3. Конкретный похожий проект из профиля — выбери из раздела "Портфолио" тот кейс, который ближе всего к задаче заказчика. Называй проекты конкретно (не "для магазинов", а "для Ozon и Wildberries"; не "для бизнеса", а что именно делал). Одно предложение.
4. Что можешь сделать — одним предложением, без перечисления ТЗ клиента обратно ему
5. Мягкий призыв к действию ("Обсудим?")

## Правила:
- 4-6 предложений, 300-500 символов
- Бери кейсы и опыт строго из профиля фрилансера — не выдумывай проекты, не обобщай их
- Не выдумывай цифры ("15 проектов", "50 клиентов") — только факты из профиля
- Не пересказывай ТЗ клиента — он и так знает что написал
- Не указывай цену
- Предлагай показать кейс вместо голословных утверждений
- НЕ пиши "Вы" с большой буквы — только "вы" с маленькой
- НЕ пиши "Здравствуйте" — пиши "Привет"
- НЕ пиши "Готов обсудить детали сотрудничества" — пиши "Обсудим?"
- Никакого AI-стиля, канцелярита, шаблонных фраз

## Ответь ТОЛЬКО текстом сообщения, без кавычек и пояснений."""


class ReplyGenerator:
    """
    Генератор автоответов: Gemini через Antigravity Proxy, fallback на DeepSeek.
    Proxy использует Anthropic-совместимый API (/v1/messages).
    """

    def __init__(self):
        self._gemini_url = settings.gemini_proxy_url
        self._gemini_key = settings.gemini_api_key
        self._fallback_model = settings.deepseek_model
        self._timeout = settings.ai_request_timeout

        self._gemini_client: Optional[httpx.AsyncClient] = None
        self._fallback_client: Optional[httpx.AsyncClient] = None

    async def _get_gemini_client(self) -> Optional[httpx.AsyncClient]:
        """Клиент для Gemini proxy (Anthropic API формат)"""
        if not self._gemini_url or not self._gemini_key:
            return None
        if self._gemini_client is None or self._gemini_client.is_closed:
            self._gemini_client = httpx.AsyncClient(
                base_url=self._gemini_url.rstrip("/"),
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "x-api-key": self._gemini_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
            )
        return self._gemini_client

    async def _get_fallback_client(self) -> httpx.AsyncClient:
        """Клиент для DeepSeek через OpenRouter (fallback)"""
        if self._fallback_client is None or self._fallback_client.is_closed:
            self._fallback_client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/leadhunter",
                    "X-Title": "LeadHunter ReplyGen"
                }
            )
        return self._fallback_client

    async def close(self):
        """Закрыть HTTP-клиенты"""
        for client in (self._gemini_client, self._fallback_client):
            if client and not client.is_closed:
                await client.aclose()

    async def generate_reply(
        self,
        lead_text: str,
        style: str = "деловой",
        freelancer_profile: Optional[Any] = None,
        classification: Optional[Dict[str, Any]] = None,
        feedback: Optional[str] = None,
        previous_draft: Optional[str] = None,
    ) -> str:
        """
        Сгенерировать один черновик автоответа.

        Args:
            lead_text: Текст сообщения заказчика
            style: Не используется (оставлен для обратной совместимости)
            freelancer_profile: Объект FreelancerProfile из БД (опционально)
            classification: Данные классификации (опционально, для контекста)
            feedback: Комментарий оператора к предыдущему черновику (опционально)
            previous_draft: Текст предыдущего черновика для контекста (опционально)

        Returns:
            Текст черновика ответа
        """
        ## Формирование секции профиля
        profile_section = self._format_profile(freelancer_profile)

        ## Промпт
        prompt = REPLY_PROMPT.format(
            lead_text=lead_text[:1500],
            profile_section=profile_section,
        )

        ## Добавляем фидбек оператора если есть
        if feedback and previous_draft:
            prompt += f"\n\n## Предыдущий черновик:\n{previous_draft[:1000]}"
            prompt += f"\n\n## Комментарий оператора (учти при генерации):\n{feedback}"
        elif feedback:
            prompt += f"\n\n## Комментарий оператора (учти при генерации):\n{feedback}"

        ## Генерация: Gemini → fallback DeepSeek
        reply = await self._generate_via_gemini(prompt)
        if reply:
            logger.info("✅ Черновик сгенерирован через Gemini")
            return reply

        reply = await self._generate_via_fallback(prompt)
        if reply:
            logger.info("✅ Черновик сгенерирован через DeepSeek fallback")
            return reply

        ## Если всё упало — шаблон-заглушка
        logger.error("❌ Не удалось сгенерировать черновик ни через один сервис")
        return self._fallback_template(lead_text)

    async def _generate_via_gemini(self, prompt: str) -> Optional[str]:
        """Генерация через Gemini proxy (Anthropic-совместимый API)"""
        client = await self._get_gemini_client()
        if not client:
            logger.debug("⏭️ Gemini proxy не настроен, пропуск")
            return None

        try:
            response = await client.post("/messages", json={
                "model": "gemini-3-flash",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
            })
            response.raise_for_status()

            data = response.json()

            ## Извлекаем текст из content блоков (Anthropic формат)
            content_blocks = data.get("content", [])
            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if block.get("type") == "text"
            ]
            content = "\n".join(text_parts).strip()

            if not content:
                logger.warning("⚠️ Gemini proxy вернул пустой ответ")
                return None

            ## Убираем кавычки если AI обернул ответ
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]

            return content

        except httpx.ConnectError:
            logger.warning("⚠️ Gemini proxy недоступен (ConnectError)")
            return None
        except httpx.TimeoutException:
            logger.warning("⚠️ Gemini proxy таймаут")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка Gemini proxy: {e}")
            return None

    async def _generate_via_fallback(self, prompt: str) -> Optional[str]:
        """Генерация через DeepSeek на OpenRouter (fallback)"""
        try:
            client = await self._get_fallback_client()

            response = await client.post("/chat/completions", json={
                "model": self._fallback_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4096,
            })
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]

            return content

        except Exception as e:
            logger.error(f"❌ Ошибка DeepSeek fallback: {e}")
            return None

    def _format_profile(self, profile: Optional[Any]) -> str:
        """Форматирование профиля фрилансера для промпта"""
        if not profile:
            return (
                "Стек: Python, aiogram, Telethon, Next.js, PostgreSQL, Docker, n8n, AI\n"
                "Специализация: Telegram боты, веб-приложения, автоматизация, AI-интеграции"
            )

        parts = []
        if profile.stack:
            parts.append(f"Стек: {profile.stack}")
        if profile.specialization:
            parts.append(f"Специализация: {profile.specialization}")
        if profile.about:
            parts.append(f"О себе: {profile.about}")
        if profile.portfolio_url:
            parts.append(f"Портфолио: {profile.portfolio_url}")
        if profile.min_budget:
            parts.append(f"Минимальный бюджет: {profile.min_budget} руб.")

        return "\n".join(parts) if parts else "Профиль не заполнен"

    def _fallback_template(self, lead_text: str) -> str:
        """Шаблон-заглушка если все AI-сервисы недоступны"""
        return "Привет! Увидел ваше сообщение — как раз занимаюсь подобным. Обсудим?"


## Синглтон генератора
_generator_instance: Optional[ReplyGenerator] = None


def get_reply_generator() -> ReplyGenerator:
    """
    Получить глобальный экземпляр генератора.

    Returns:
        ReplyGenerator (синглтон)
    """
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ReplyGenerator()
    return _generator_instance


async def cleanup_reply_generator():
    """Очистка при завершении"""
    global _generator_instance
    if _generator_instance:
        await _generator_instance.close()
        _generator_instance = None
