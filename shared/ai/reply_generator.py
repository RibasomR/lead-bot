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

## ГЛАВНОЕ ПРАВИЛО — ответь на то, что просят:
Прочитай заказ внимательно. Если автор просит конкретную информацию (опыт с технологией X, ссылки, загрузку, ответы на вопросы) — дай эту информацию в отклике. Не отклоняйся от того, что человек хочет услышать.

Если в конце заказа есть список пунктов/вопросов — ответь на каждый коротко и по делу. Это важнее шаблона.

## Структура отклика:
1. Короткое приветствие + откуда ты (видел пост в чате)
2. Ответы на конкретные вопросы/пункты заказчика (если есть)
3. Один релевантный кейс из портфолио (назови проект, что делал)
4. Закрытие (без давления)

Если заказчик не задаёт конкретных вопросов — пиши классический отклик: приветствие, кейс, предложение пообщаться.

## Как писать:
Пиши как живой человек в телеге. Короткие предложения. Без пафоса и канцелярита.
Обращение на "ты" или "вы" с маленькой буквы, по ситуации.

## Жёсткие запреты:
- НЕ используй тире (символ "—") вообще нигде
- НЕ заканчивай словом "Обсудим?" каждый раз, варьируй: "напиши, если интересно", "могу показать", "расскажу подробнее", или просто оставь без призыва
- НЕ пиши "Здравствуйте"
- НЕ пересказывай заказ клиента обратно ему ("ты писал про...", "видел что ищешь..." — максимум одна фраза)
- НЕ перечисляй весь стек через запятую
- НЕ пиши "Готов обсудить детали", "Буду рад сотрудничеству" и подобный канцелярит
- НЕ выдумывай цифры и проекты, только из портфолио
- НЕ используй слово "релевантный"
- НЕ указывай цену
- НИКОГДА не начинай два предложения подряд одинаково

## Примеры хороших сообщений (для понимания стиля, не копируй их):

Пример 1 (заказ с вопросами — "напишите: 1) опыт с n8n 2) ссылки на работы"):
"Привет! Видел пост в чате.
1) С n8n работаю плотно, делал автоответы на отзывы для 4 магазинов на Ozon и WB, всё крутится на автопилоте.
2) Вот свежий проект: echonote.ru, SaaS для AI-конспектов.
Могу показать как устроено, если актуально"

Пример 2 (заказ без вопросов — просто описание задачи):
"Привет, ты писал про бота для записи. У меня есть бот для образовательного центра, там запись на занятия, расписание, оплата через ЮKassa. Если нужно что-то подобное, напиши, скину детали"

## Формат:
Если заказчик задаёт конкретные вопросы — ответь на них, даже если выйдет длиннее. Иначе 3-5 предложений.
Ответь ТОЛЬКО текстом сообщения."""


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
            response = await client.post("/messages", json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.85,
                "max_tokens": 4096,
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
                "Специализация: Telegram боты, веб-приложения, бизнес-автоматизация, AI-интеграции\n"
                "GitHub: github.com/RibasomR\n\n"
                "Портфолио:\n\n"
                "Бизнес-автоматизация:\n"
                "- Автоматизация лидогенерации LeadHunter (github.com/RibasomR/lead-bot): мониторит 30+ Telegram-чатов, AI классифицирует заказы и генерирует персональные отклики. Оператор только нажимает «Отправить». Telethon + aiogram + DeepSeek + Gemini\n"
                "- Автоматизация ответов на отзывы для 4 маркетплейс-магазинов (Ozon/WB): AI генерирует персональные ответы на основе базы знаний магазина, работает без участия человека. n8n + LLM + RAG\n"
                "- B2B-аутрич в Telegram: автоматическая рассылка персонализированных сообщений потенциальным клиентам с учётом контекста переписки. LLM генерирует текст, антибан-система для безопасности аккаунтов\n"
                "- Сбор B2B-контактов из 2ГИС (github.com/RibasomR/2gis-parser): Telegram-бот собирает базы организаций по запросу, несколько городов за раз, экспорт в Excel. Антидетект-браузер, обход защиты\n\n"
                "Telegram-боты:\n"
                "- Бот для образовательного центра GO IT: воронка записи на курсы, расписание, CRM с уведомлениями\n"
                "- Трекер финансов с голосовым вводом (github.com/RibasomR/finance-bot): говоришь «потратил 500 на такси», AI распознаёт речь и разбирает транзакцию. Статистика, категории, Excel-экспорт\n"
                "- Игровой бот @PathtoAbundance_bot: 22 игровых локации, интеграция оплаты через ЮKassa, PDF-отчёты по прохождению\n"
                "- VPN-сервис: бот для управления подпиской, автовыдача конфигов VLESS Reality, панель администратора\n\n"
                "Веб:\n"
                "- echonote.ru: SaaS-сервис для создания AI-конспектов из YouTube-видео. Фулстек: Next.js + FastAPI + мульти-агентная LLM-система\n"
                "- Лендинг онлайн-школы: каталог курсов с фильтрацией, запись, аналитика источников трафика (UTM), SEO-оптимизация. Next.js"
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
