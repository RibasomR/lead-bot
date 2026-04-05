"""
## Модуль формирования лид-карточек (v2)
Компактные карточки с данными классификатора, черновиком ответа и inline-кнопками.
"""

import re
from html import escape as html_escape
from typing import Optional, List
from datetime import timezone, timedelta

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold, hcode, hitalic, hlink

from shared.database.models import Lead, Chat, LeadAIData
from shared.locales import t

## Разрешённые HTML-теги для Telegram (всё остальное удаляется)
_ALLOWED_TAGS_RE = re.compile(
    r'<(?!/?(b|i|a|code|pre|u|s|strike|del|blockquote|tg-spoiler|tg-emoji)\b)[^>]*>',
    re.IGNORECASE,
)


def _sanitize_html(text: str) -> str:
    """
    Удаляет из текста все HTML-теги, кроме разрешённых Telegram-тегов.

    :param text: Входной текст с HTML
    :return: Текст только с безопасными тегами
    """
    return _ALLOWED_TAGS_RE.sub("", text)


def _strip_html_tags(text: str) -> str:
    """
    Удаляет все HTML-теги из текста (для подсчёта длины).

    :param text: HTML-текст
    :return: Чистый текст без тегов
    """
    return re.sub(r'<[^>]+>', '', text)

## Таймзона оператора (UTC+7)
OPERATOR_TZ = timezone(timedelta(hours=7))


## Формирование компактной лид-карточки v2
def format_lead_card(
    lead: Lead,
    ai_data: Optional[LeadAIData] = None,
    chat: Optional[Chat] = None,
    lang: str = "ru",
) -> str:
    """
    Компактная карточка лида с данными классификатора и черновиком.

    Args:
        lead: Объект лида из БД
        ai_data: Данные анализа от ИИ (опционально)
        chat: Объект чата (если None — берётся из lead.chat)

    Returns:
        Отформатированный HTML-текст карточки
    """
    chat = chat or getattr(lead, "chat", None)
    lines = []

    ## Заголовок: summary + оценка релевантности
    title = ai_data.summary[:500] if ai_data and ai_data.summary else t("leads.card.new_lead", lang)
    if ai_data and ai_data.relevance_score:
        score = int(ai_data.relevance_score)
        lines.append(f"🎯 {hbold(title)} ({score}/10)")
    else:
        lines.append(f"🎯 {hbold(title)}")

    lines.append("")

    ## Чат + автор (компактно, с экранированием)
    if chat:
        chat_str = html_escape(chat.title) if chat.title else "—"
        if hasattr(chat, "username") and chat.username:
            chat_str += f" (@{html_escape(chat.username)})"
        lines.append(f"💬 {chat_str}")

    author_parts = []
    if lead.author_name:
        author_parts.append(html_escape(lead.author_name))
    if lead.author_username:
        author_parts.append(f"@{html_escape(lead.author_username)}")
    if author_parts:
        lines.append(f"👤 {' · '.join(author_parts)}")

    lines.append("")

    ## Текст сообщения (может содержать HTML из Telethon entities)
    message_text = lead.message_text
    ## Конвертим markdown **text** → <b>text</b> (для старых лидов без HTML-тегов)
    message_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', message_text, flags=re.DOTALL)
    message_text = re.sub(r'(?<!\w)__(.+?)__(?!\w)', r'<i>\1</i>', message_text, flags=re.DOTALL)
    ## Убираем осиротевшие маркеры (нечётное кол-во ** или __)
    message_text = re.sub(r'\*\*', '', message_text)
    ## Удаляем небезопасные HTML-теги, оставляя только Telegram-разрешённые
    message_text = _sanitize_html(message_text)
    plain_text = _strip_html_tags(message_text)
    if len(plain_text) > 600:
        ## Для длинных сообщений — обрезаем plain text, чтобы не ломать HTML-теги
        message_text = html_escape(plain_text[:600]) + "…"
    lines.append(t("leads.card.message_label", lang))
    lines.append(message_text)

    ## Ссылка (с разделителем)
    if lead.message_url:
        lines.append("")
        lines.append(f"🔗 {hlink('Открыть в чате', lead.message_url)}")

    ## Стек
    if lead.stack_tags:
        lines.append(f"🔧 {hcode(lead.stack_tags)}")

    ## Черновик ответа
    draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)
    draft_display = None
    if draft:
        lines.append("")
        lines.append(t("leads.card.draft_label", lang))
        draft_display = draft if len(draft) <= 3000 else draft[:3000] + "…"
        lines.append(hitalic(draft_display))

    ## Проверка лимита Telegram (4096 символов) — обрезаем при превышении
    result = "\n".join(lines)
    result_plain_len = len(_strip_html_tags(result))
    if result_plain_len > 4000:
        ## Сначала пробуем обрезать черновик
        if draft_display and len(draft_display) > 1000:
            lines = [l for l in lines if l != hitalic(draft_display)]
            draft_display = draft_display[:1000] + "…"
            lines.append(hitalic(draft_display))
            result = "\n".join(lines)
            result_plain_len = len(_strip_html_tags(result))

        ## Если всё ещё не влезает — обрезаем текст сообщения
        if result_plain_len > 4000:
            short_text = html_escape(_strip_html_tags(lead.message_text)[:300]) + "…"
            lines = [short_text if l == message_text else l for l in lines]
            result = "\n".join(lines)

    return result


## Клавиатура лид-карточки v2 (для просмотра из списка)
def get_lead_card_keyboard(
    lead_id: int,
    has_draft: bool = False,
    has_ai_data: bool = False,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """
    Inline-клавиатура для действий с лидом (просмотр из списка).

    Args:
        lead_id: ID лида
        has_draft: Есть ли черновик ответа
        has_ai_data: Есть ли данные AI анализа

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    if has_draft:
        ## Черновик есть → Отправить / Перегенерировать / Редактировать / Пропустить
        builder.button(
            text=t("leads.btn.send", lang),
            callback_data=f"lead:send_draft:{lead_id}"
        )
        builder.button(
            text=t("leads.btn.regenerate", lang),
            callback_data=f"lead:regenerate:{lead_id}"
        )
        builder.button(
            text=t("leads.btn.edit", lang),
            callback_data=f"lead:edit_draft:{lead_id}"
        )
    else:
        ## Черновика нет
        builder.button(
            text=t("leads.btn.generate", lang),
            callback_data=f"lead:regenerate:{lead_id}"
        )

    ## Пропустить + Список
    builder.button(
        text=t("leads.btn.skip", lang),
        callback_data=f"lead:ignore:{lead_id}"
    )
    builder.button(text=t("leads.btn.list", lang), callback_data="menu:leads")

    ## Раскладка кнопок
    if has_draft:
        builder.adjust(1, 2, 1, 1)
    else:
        builder.adjust(1, 1, 1)

    return builder.as_markup()


## Клавиатура push-уведомления (без навигации и списка)
def get_lead_push_keyboard(
    lead_id: int,
    has_draft: bool = False,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """
    Inline-клавиатура для push-уведомления о новом лиде.
    Без кнопок навигации (стрелки, список).

    Args:
        lead_id: ID лида
        has_draft: Есть ли черновик ответа

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    if has_draft:
        builder.button(
            text=t("leads.btn.send", lang),
            callback_data=f"lead:send_draft:{lead_id}"
        )
        builder.button(
            text=t("leads.btn.regenerate", lang),
            callback_data=f"lead:regenerate:{lead_id}"
        )
        builder.button(
            text=t("leads.btn.edit", lang),
            callback_data=f"lead:edit_draft:{lead_id}"
        )
        builder.button(
            text=t("leads.btn.skip", lang),
            callback_data=f"lead:ignore:{lead_id}"
        )
        builder.adjust(1, 2, 1)
    else:
        builder.button(
            text=t("leads.btn.generate", lang),
            callback_data=f"lead:regenerate:{lead_id}"
        )
        builder.button(
            text=t("leads.btn.skip", lang),
            callback_data=f"lead:ignore:{lead_id}"
        )
        builder.adjust(1, 1)

    return builder.as_markup()


## Клавиатура подтверждения отправки
def get_send_confirmation_keyboard(
    lead_id: int,
    account_id: int,
    variant_index: Optional[int] = None,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения отправки.

    Args:
        lead_id: ID лида
        account_id: ID аккаунта
        variant_index: Индекс варианта (deprecated, для совместимости)

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    callback_data = f"lead:send_confirm:{lead_id}:{account_id}"
    if variant_index is not None:
        callback_data += f":{variant_index}"

    builder.button(text=t("leads.btn.send", lang), callback_data=callback_data)
    builder.button(text=t("leads.btn.edit", lang), callback_data=f"lead:edit_text:{lead_id}")
    builder.button(text=t("leads.btn.cancel", lang), callback_data=f"lead:show:{lead_id}")

    builder.adjust(1)
    return builder.as_markup()


## Клавиатура выбора варианта ответа (deprecated, оставлено для совместимости)
def get_reply_variants_keyboard(
    lead_id: int,
    num_variants: int = 3,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Deprecated: используйте get_lead_card_keyboard с has_draft=True"""
    builder = InlineKeyboardBuilder()

    for i in range(num_variants):
        builder.button(
            text=f"✉️ {t('leads.variant_n', lang, n=i + 1)}",
            callback_data=f"lead:use_variant:{lead_id}:{i}"
        )

    builder.button(text=t("menu.back", lang), callback_data=f"lead:show:{lead_id}")
    builder.adjust(1)
    return builder.as_markup()


## Форматирование списка лидов
def format_leads_list(
    leads: List[Lead],
    page: int,
    total_pages: int,
    lang: str = "ru",
) -> str:
    """
    Список лидов с пагинацией.

    Args:
        leads: Список лидов
        page: Текущая страница
        total_pages: Всего страниц
        lang: Язык интерфейса

    Returns:
        HTML-текст списка
    """
    if not leads:
        return t("leads.no_leads", lang)

    lines = [
        hbold(t("leads.title", lang, page=page + 1, total=total_pages)),
        ""
    ]

    for lead in leads:
        status_emoji = {
            "new": "🆕", "viewed": "👁",
            "replied": "✅", "ignored": "🚫"
        }.get(lead.status, "❓")

        plain_preview = re.sub(r'<[^>]+>', '', lead.message_text)
        preview = html_escape(plain_preview[:50] + "…" if len(plain_preview) > 50 else plain_preview)
        local_time = lead.created_at.replace(tzinfo=timezone.utc).astimezone(OPERATOR_TZ)
        date_str = local_time.strftime("%d.%m %H:%M")

        lines.append(f"{status_emoji} {hbold(f'#{lead.id}')} | {date_str}")
        lines.append(f"   {preview}")
        lines.append("")

    return "\n".join(lines)


## Клавиатура списка лидов
def get_leads_list_keyboard(
    leads: List[Lead],
    page: int,
    total_pages: int,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """
    Клавиатура списка лидов с пагинацией.

    Args:
        leads: Список лидов
        page: Текущая страница
        total_pages: Всего страниц

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    for lead in leads:
        status_emoji = {
            "new": "🆕", "viewed": "👁",
            "replied": "✅", "ignored": "🚫"
        }.get(lead.status, "❓")

        builder.button(
            text=f"{status_emoji} #{lead.id}",
            callback_data=f"lead:show:{lead.id}"
        )

    ## Пагинация
    if page > 0:
        builder.button(text="◀️", callback_data=f"leads:page:{page - 1}")
    builder.button(text=f"{page + 1}/{total_pages}", callback_data="pagination:current")
    if page < total_pages - 1:
        builder.button(text="▶️", callback_data=f"leads:page:{page + 1}")

    builder.button(text=t("menu.back_to_menu", lang), callback_data="menu:main")

    ## Лиды по 2 в строке, затем пагинация, затем меню
    num_leads = len(leads)
    rows = [2] * (num_leads // 2)
    if num_leads % 2:
        rows.append(1)
    nav_count = 1 + (1 if page > 0 else 0) + (1 if page < total_pages - 1 else 0)
    rows.append(nav_count)
    rows.append(1)

    builder.adjust(*rows)
    return builder.as_markup()
