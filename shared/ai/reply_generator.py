"""
Генератор автоответов через OpenRouter.
Модель задаётся через REPLY_MODEL в .env.
"""

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
    """Генератор автоответов через OpenRouter."""

    def __init__(self):
        self._model = settings.reply_model
        self._timeout = settings.ai_request_timeout
        self._base_url = settings.reply_api_base
        self._api_key = settings.reply_api_key or settings.openrouter_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/RibasomR/lead-bot",
                    "X-Title": "LeadHunter ReplyGen"
                }
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def generate_reply(
        self,
        lead_text: str,
        style: str = "деловой",
        freelancer_profile: Optional[Any] = None,
        classification: Optional[Dict[str, Any]] = None,
        feedback: Optional[str] = None,
        previous_draft: Optional[str] = None,
    ) -> str:
        profile_section = self._format_profile(freelancer_profile)

        prompt = REPLY_PROMPT.format(
            lead_text=lead_text[:1500],
            profile_section=profile_section,
        )

        if feedback and previous_draft:
            prompt += f"\n\n## Предыдущий черновик:\n{previous_draft[:1000]}"
            prompt += f"\n\n## Комментарий оператора (учти при генерации):\n{feedback}"
        elif feedback:
            prompt += f"\n\n## Комментарий оператора (учти при генерации):\n{feedback}"

        try:
            client = await self._get_client()
            response = await client.post("/chat/completions", json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4096,
            })
            response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"].strip()

            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]

            logger.info(f"✅ Черновик сгенерирован через {self._model}")
            return content

        except Exception as e:
            logger.error(f"❌ Ошибка генерации ответа: {e}")
            return self._fallback_template()

    def _format_profile(self, profile: Optional[Any]) -> str:
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

    def _fallback_template(self) -> str:
        return "Привет! Увидел ваше сообщение — как раз занимаюсь подобным. Обсудим?"


## Синглтон генератора
_generator_instance: Optional[ReplyGenerator] = None


def get_reply_generator() -> ReplyGenerator:
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ReplyGenerator()
    return _generator_instance


async def cleanup_reply_generator():
    global _generator_instance
    if _generator_instance:
        await _generator_instance.close()
        _generator_instance = None
