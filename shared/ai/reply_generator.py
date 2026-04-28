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
REPLY_PROMPT = """Ты пишешь первое сообщение от имени фрилансера человеку в личку Telegram. Он оставил заказ в чате, ты откликаешься.

## Заказ:
{lead_text}

## Кто ты:
{profile_section}

## Как писать:
Пиши как живой человек в телеге. Короткие предложения. Без пафоса и канцелярита.
Обращение на "ты" или "вы" с маленькой буквы, по ситуации.

## Что должно быть в сообщении:
- Понятно, зачем ты пишешь (видел заказ в чате)
- Один конкретный кейс из портфолио, который похож на задачу. Назови проект, что делал, для кого
- Предложение пообщаться, но без давления

## Жёсткие запреты:
- НЕ используй тире (символ "—") вообще нигде
- НЕ заканчивай словом "Обсудим?" каждый раз, варьируй: "напиши, если интересно", "могу показать", "расскажу подробнее", или просто оставь без призыва
- НЕ пиши "Здравствуйте"
- НЕ пересказывай заказ клиента обратно ему
- НЕ перечисляй весь стек через запятую
- НЕ пиши "Готов обсудить детали", "Буду рад сотрудничеству" и подобный канцелярит
- НЕ выдумывай цифры и проекты, только из портфолио
- НЕ используй слово "релевантный"
- НЕ указывай цену
- НИКОГДА не начинай два предложения подряд одинаково

## Примеры хороших сообщений (для понимания стиля, не копируй их):

Пример 1 (на заказ по n8n автоматизации):
"Привет! Видел твой пост про автоматизацию каналов. Я недавно делал похожую штуку: автоответы на отзывы для 4 магазинов на Ozon и WB, всё на n8n + AI, работает на автопилоте. Могу показать как это устроено, если актуально"

Пример 2 (на заказ по боту):
"Привет, ты писал про бота для записи. У меня есть бот для образовательного центра, там запись на занятия, расписание, оплата через ЮKassa. Если нужно что-то подобное, напиши, скину детали"

Пример 3 (на заказ по веб-разработке):
"Привет! Заметил твой пост про MVP. Делаю фулстек на Next.js + FastAPI. Из похожего: собрал echonote.ru, это SaaS для AI-конспектов из видео, с нуля до прода. Расскажу подробнее, если интересно"

## Формат:
3-5 предложений, 200-400 символов. Ответь ТОЛЬКО текстом сообщения."""


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
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
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
            response = await client.post("/v1/messages", json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.85,
                "max_tokens": 1024,
                "thinking": {"type": "disabled"},
            })
            response.raise_for_status()

            data = response.json()
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content = block["text"].strip()
                    break

            if not content:
                logger.warning(f"⚠️ Пустой ответ от {self._model}, content blocks: {data.get('content', [])}")
                return self._fallback_template()

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
                "Стек: Python, aiogram, Telethon, Next.js, FastAPI, PostgreSQL, Docker, n8n\n"
                "Специализация: Telegram боты, веб-приложения, автоматизация, AI-интеграции\n\n"
                "Портфолио:\n"
                "- echonote.ru: SaaS для AI-конспектов из YouTube-видео (Next.js + FastAPI + мульти-агентная LLM система)\n"
                "- @PathtoAbundance_bot: игровой Telegram-бот с оплатой через ЮKassa, 22 игровых локации, PDF-отчёты\n"
                "- Автоответы на отзывы Ozon/WB: n8n + Groq + RAG на pgvector, 4 магазина на автопилоте\n"
                "- Парсер 2GIS: Telegram-бот для парсинга организаций с экспортом в Excel (Playwright stealth)\n"
                "- Бот для образовательного центра GO IT: воронка записи на курсы, CRM, уведомления\n"
                "- VPN-сервис с Telegram-ботом: VLESS Reality, панель Remnawave, IP-Lock\n"
                "- B2B outreach бот: автоматический аутрич в Telegram с LLM-контекстом и антибаном\n"
                "- Лендинг для онлайн-школы: Next.js, каталог курсов, UTM-аналитика, SEO"
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
