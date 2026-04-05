"""
## Хендлеры работы с лидами
Обработка просмотра, навигации и действий с лидами.
"""

from typing import Optional
from datetime import datetime, timedelta
import json

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import get_main_menu_keyboard
from admin_bot.lead_card import (
    format_lead_card,
    get_lead_card_keyboard,
    format_leads_list,
    get_leads_list_keyboard,
    get_reply_variants_keyboard,
    get_send_confirmation_keyboard
)
from admin_bot.states import LeadStates, EditDraftStates, RegenerateDraftStates
from shared.database.engine import get_session
from shared.database.crud import (
    get_lead_by_id,
    get_leads_by_status,
    get_leads_by_date_range,
    update_lead_status,
    update_lead,
    create_reply,
    get_all_accounts,
    get_account_by_id,
    get_lead_ai_data,
    create_lead_ai_data,
    update_lead_ai_data,
    get_freelancer_profile
)
from shared.database.models import Lead, LeadStatus, CommunicationStyle
from shared.ai.ai_advisor import AIAdvisor
from shared.ai.reply_generator import get_reply_generator
from shared.locales import t
from config import settings

import logging
logger = logging.getLogger(__name__)


router = Router(name="leads_router")

# Константы
LEADS_PER_PAGE = 8


## Команда /leads
@router.message(Command("leads"), OperatorFilter())
async def cmd_leads(message: Message, lang: str = "ru"):
    """
    Показывает список всех лидов (кроме ignored) с пагинацией.
    """
    await _show_leads_page(message, page=0, edit=False, lang=lang)


async def _show_leads_page(message_or_callback, page: int, edit: bool = True, lang: str = "ru"):
    """Общая логика отображения страницы лидов."""
    from shared.database.crud import get_all_leads

    async with get_session() as session:
        all_leads = await get_all_leads(session, limit=1000)

    if not all_leads:
        text = t("leads.empty", lang)
        kb = get_main_menu_keyboard(lang)
        if edit:
            await message_or_callback.message.edit_text(text, reply_markup=kb)
        else:
            await message_or_callback.answer(text, reply_markup=kb)
        return

    total_pages = max(1, (len(all_leads) + LEADS_PER_PAGE - 1) // LEADS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * LEADS_PER_PAGE
    page_leads = all_leads[start_idx:start_idx + LEADS_PER_PAGE]

    text = format_leads_list(page_leads, page, total_pages)
    keyboard = get_leads_list_keyboard(page_leads, page, total_pages)

    if edit:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard)
    else:
        await message_or_callback.answer(text, reply_markup=keyboard)


## Callback меню лидов
@router.callback_query(F.data == "menu:leads", OperatorFilter())
async def callback_leads_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик callback меню лидов.
    """
    await _show_leads_page(callback, page=0, lang=lang)
    await callback.answer()


## Callback пагинации лидов
@router.callback_query(F.data.startswith("leads:page:"), OperatorFilter())
async def callback_leads_page(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик перехода по страницам лидов.
    """
    try:
        page = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer(t("leads.nav_error", lang))
        return

    await _show_leads_page(callback, page=page, lang=lang)
    await callback.answer()


## Callback просмотра конкретного лида
@router.callback_query(F.data.startswith("lead:show:"), OperatorFilter())
async def callback_show_lead(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает подробную карточку лида.
    Автоматически обновляет статус на 'viewed'.
    """
    lead_id = int(callback.data.split(":")[2])
    await _show_lead_card(callback, lead_id, lang=lang)


async def _show_lead_card(callback: CallbackQuery, lead_id: int, lang: str = "ru"):
    """Общая логика показа карточки лида (используется в show/prev/next)."""
    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)

        if not lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        if lead.status == LeadStatus.NEW.value:
            await update_lead_status(session, lead_id, LeadStatus.VIEWED.value)
            await session.commit()
            lead.status = LeadStatus.VIEWED.value

        ## v2: компактная карточка с черновиком
        ai_data = lead.ai_data
        draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

        text = format_lead_card(lead, ai_data)
        keyboard = get_lead_card_keyboard(
            lead_id,
            has_draft=bool(draft),
            has_ai_data=ai_data is not None
        )

    await callback.message.edit_text(text, reply_markup=keyboard)
    try:
        await callback.answer()
    except Exception:
        pass


## Callback отправки черновика (v2)
@router.callback_query(F.data.startswith("lead:send_draft:"), OperatorFilter())
async def callback_send_draft(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Отправить черновик ответа сразу. Автовыбор аккаунта с ролью reply/both.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        ai_data = lead.ai_data
        draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

        if not draft:
            await callback.answer(t("leads.no_draft", lang), show_alert=True)
            return

        accounts = await get_all_accounts(session, enabled_only=True)
        if not accounts:
            await callback.answer(t("leads.no_accounts", lang), show_alert=True)
            return

        ## Автовыбор аккаунта: reply > both > первый доступный
        account = next(
            (a for a in accounts if a.role == "reply"),
            next(
                (a for a in accounts if a.role == "both"),
                accounts[0]
            )
        )

        await callback.answer(t("leads.sending", lang), show_alert=False)

        ## Отправляем сразу без подтверждения
        success, error_code = await send_message_via_listener(
            lead=lead,
            account=account,
            reply_text=draft,
            fast_mode=False
        )

        if success:
            await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)
            await create_reply(
                session,
                lead_id=lead_id,
                account_id=account.id,
                style_used=account.style_default,
                reply_text=draft,
                fast_mode_used=False,
                was_successful=True
            )
            await session.commit()

            await callback.message.edit_text(
                t("leads.sent_ok", lang, account=account.label),
                reply_markup=get_main_menu_keyboard(lang)
            )
        elif error_code == "NO_DM_ACCESS":
            chat_title = lead.chat.title if lead.chat else "?"
            lines = [t("leads.no_dm_access", lang)]
            lines.append(t("leads.no_dm_details", lang))
            lines.append(f"💬 {chat_title}")

            if lead.message_url:
                lines.append(f"🔗 <a href=\"{lead.message_url}\">{t('leads.card.open_in_chat', lang)}</a>")

            lines.append(f"\n{t('leads.draft_copy_label', lang)}")
            lines.append(f"<pre>{draft}</pre>")

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t("leads.btn.sent_manually", lang),
                    callback_data=f"lead:mark_replied:{lead_id}"
                )],
            ])

            await callback.message.edit_text(
                "\n".join(lines),
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        else:
            await callback.message.edit_text(
                t("leads.send_error", lang),
                reply_markup=get_main_menu_keyboard(lang)
            )

    await state.clear()


## Callback "Отправил вручную" -- помечает лид как replied
@router.callback_query(F.data.startswith("lead:mark_replied:"), OperatorFilter())
async def callback_mark_replied(callback: CallbackQuery, lang: str = "ru"):
    """Оператор отправил сообщение вручную -- помечаем лид как replied."""
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)
        await session.commit()

    await callback.message.edit_text(
        t("leads.marked_replied", lang, lead_id=lead_id),
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback.answer()


## Callback редактирования черновика (v2)
@router.callback_query(F.data.startswith("lead:edit_draft:"), OperatorFilter())
async def callback_edit_draft(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Переводит в FSM для редактирования текста черновика.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        ai_data = lead.ai_data
        draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

    await state.update_data(lead_id=lead_id)
    await state.set_state(EditDraftStates.waiting_for_edited_text)

    text = t("leads.edit_draft_title", lang)
    if draft:
        text += t("leads.edit_current", lang, draft=draft)
    text += t("leads.edit_prompt", lang)

    await callback.message.edit_text(text)
    await callback.answer()


## Обработка отредактированного текста черновика (v2)
@router.message(EditDraftStates.waiting_for_edited_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_edited_draft(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Сохраняет отредактированный черновик и показывает обновлённую карточку.
    """
    data = await state.get_data()
    lead_id = data.get("lead_id")

    if not lead_id:
        await message.answer(t("leads.edit_no_lead", lang))
        await state.clear()
        return

    new_text = message.text.strip()

    async with get_session() as session:
        await update_lead(session, lead_id, draft_reply=new_text)
        await session.commit()

        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data

        card_text = format_lead_card(lead, ai_data)
        keyboard = get_lead_card_keyboard(
            lead_id, has_draft=True, has_ai_data=ai_data is not None
        )

    await state.clear()
    await message.answer(
        t("leads.edit_saved", lang, card=card_text),
        reply_markup=keyboard
    )


## Callback перегенерации черновика -- спрашиваем комментарий
@router.callback_query(F.data.startswith("lead:regenerate:"), OperatorFilter())
async def callback_regenerate_draft(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Спрашивает комментарий оператора перед перегенерацией черновика.
    Если черновика ещё нет -- генерирует сразу без вопросов.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        ## Если черновика ещё нет -- генерируем сразу
        current_draft = lead.draft_reply or (lead.ai_data.generated_reply if lead.ai_data else None)
        if not current_draft:
            await callback.answer(t("leads.regen_waiting", lang))
            await _do_regenerate(callback, session, lead, feedback=None)
            return

    ## Черновик есть -- спрашиваем фидбек
    await state.set_state(RegenerateDraftStates.waiting_for_feedback)
    await state.update_data(regenerate_lead_id=lead_id)
    await callback.message.answer(t("leads.regen_feedback_prompt", lang))
    await callback.answer()


## Обработка отмены во время перегенерации черновика
@router.message(Command("cancel"), RegenerateDraftStates.waiting_for_feedback, OperatorFilter())
async def cancel_regenerate_draft(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет перегенерацию черновика по /cancel.
    """
    await state.clear()
    await message.answer(
        t("leads.regen_cancel", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )


## Обработка комментария оператора для перегенерации
@router.message(RegenerateDraftStates.waiting_for_feedback, OperatorFilter())
async def handle_regenerate_feedback(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Получает комментарий оператора и перегенерирует черновик с его учётом.
    """
    if message.text and message.text.startswith("/") and message.text.strip() != "-":
        await state.clear()
        await message.answer(t("leads.regen_cancel", lang))
        return

    data = await state.get_data()
    lead_id = data.get("regenerate_lead_id")
    await state.clear()

    if not lead_id:
        await message.answer(t("leads.regen_not_found", lang))
        return

    feedback = message.text.strip() if message.text else None
    if feedback == "-":
        feedback = None

    status_msg = await message.answer(t("leads.regen_in_progress", lang))

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await status_msg.edit_text(t("leads.regen_not_found", lang))
            return

        await _do_regenerate_with_message(status_msg, session, lead, feedback=feedback)


async def _do_regenerate(
    callback: CallbackQuery, session, lead, feedback: Optional[str] = None
):
    """Общая логика перегенерации черновика (из callback)."""
    lead_id = lead.id
    ai_data = lead.ai_data

    style = "деловой"
    if ai_data and ai_data.tone_recommendation:
        style = ai_data.tone_recommendation

    profile = await get_freelancer_profile(session)
    previous_draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

    try:
        reply_gen = get_reply_generator()
        draft = await reply_gen.generate_reply(
            lead_text=lead.message_text,
            style=style,
            freelancer_profile=profile,
            feedback=feedback,
            previous_draft=previous_draft,
        )

        await update_lead(session, lead_id, draft_reply=draft)

        if ai_data:
            await update_lead_ai_data(session, lead_id, generated_reply=draft)

        await session.commit()

        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data

        text = format_lead_card(lead, ai_data)
        keyboard = get_lead_card_keyboard(
            lead_id, has_draft=True, has_ai_data=ai_data is not None
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка генерации черновика для лида #{lead_id}: {e}")
        await callback.answer(
            t("leads.regen_error", "ru", error=str(e)[:80]),
            show_alert=True
        )


async def _do_regenerate_with_message(
    status_msg: Message, session, lead, feedback: Optional[str] = None
):
    """Общая логика перегенерации черновика (из текстового сообщения)."""
    lead_id = lead.id
    ai_data = lead.ai_data

    style = "деловой"
    if ai_data and ai_data.tone_recommendation:
        style = ai_data.tone_recommendation

    profile = await get_freelancer_profile(session)
    previous_draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

    try:
        reply_gen = get_reply_generator()
        draft = await reply_gen.generate_reply(
            lead_text=lead.message_text,
            style=style,
            freelancer_profile=profile,
            feedback=feedback,
            previous_draft=previous_draft,
        )

        await update_lead(session, lead_id, draft_reply=draft)
        if ai_data:
            await update_lead_ai_data(session, lead_id, generated_reply=draft)
        await session.commit()

        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data

        text = format_lead_card(lead, ai_data)
        keyboard = get_lead_card_keyboard(
            lead_id, has_draft=True, has_ai_data=ai_data is not None
        )

        await status_msg.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка генерации черновика для лида #{lead_id}: {e}")
        await status_msg.edit_text(t("leads.regen_error", "ru", error=str(e)[:80]))


## Callback добавления автора в ЧС (v2)
@router.callback_query(F.data.startswith("lead:blacklist_author:"), OperatorFilter())
async def callback_blacklist_author(callback: CallbackQuery, lang: str = "ru"):
    """
    Помечает автора лида в чёрный список.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        author_info = lead.author_username or lead.author_name or str(lead.author_id)

        await update_lead_status(session, lead_id, LeadStatus.IGNORED.value)
        await session.commit()

        logger.info(f"Автор '{author_info}' добавлен в ЧС (лид #{lead_id})")

    await callback.message.edit_text(
        t("leads.author_blacklisted", lang, author=author_info, lead_id=lead_id),
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback.answer()


## Callback запроса анализа ИИ
@router.callback_query(F.data.startswith("lead:request_ai:"), OperatorFilter())
async def callback_request_ai(callback: CallbackQuery, lang: str = "ru"):
    """
    Запрашивает анализ лида у AI Advisor.
    """
    lead_id = int(callback.data.split(":")[2])

    await callback.answer(t("leads.ai_requesting", lang), show_alert=False)

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)

        if not lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        existing_ai_data = await get_lead_ai_data(session, lead_id)

        try:
            ai_advisor = AIAdvisor(
                api_key=settings.openrouter_api_key,
                primary_model=settings.ai_model_primary,
                secondary_model=settings.ai_model_secondary
            )

            analysis = await ai_advisor.score_lead(lead.message_text)

            if existing_ai_data:
                from shared.database.crud import update_lead_ai_data
                await update_lead_ai_data(
                    session,
                    lead_id=lead_id,
                    summary=analysis.get("summary"),
                    quality_score=analysis.get("quality_score"),
                    tone_recommendation=analysis.get("tone_recommendation"),
                    price_min=analysis.get("price_min"),
                    price_max=analysis.get("price_max"),
                    raw_response=json.dumps(analysis, ensure_ascii=False),
                    ai_model_used=settings.ai_model_primary
                )
            else:
                await create_lead_ai_data(
                    session,
                    lead_id=lead_id,
                    summary=analysis.get("summary"),
                    quality_score=analysis.get("quality_score"),
                    tone_recommendation=analysis.get("tone_recommendation"),
                    price_min=analysis.get("price_min"),
                    price_max=analysis.get("price_max"),
                    raw_response=json.dumps(analysis, ensure_ascii=False),
                    ai_model_used=settings.ai_model_primary
                )

            await session.commit()

            lead = await get_lead_by_id(session, lead_id, load_relations=True)
            ai_data = lead.ai_data
            draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

            text = format_lead_card(lead, ai_data)
            keyboard = get_lead_card_keyboard(
                lead_id, has_draft=bool(draft), has_ai_data=ai_data is not None
            )

            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer(t("leads.ai_done", lang), show_alert=False)

        except Exception as e:
            await callback.answer(
                t("leads.ai_error", lang, error=str(e)[:100]),
                show_alert=True
            )


## Callback обновления анализа ИИ
@router.callback_query(F.data.startswith("lead:refresh_ai:"), OperatorFilter())
async def callback_refresh_ai(callback: CallbackQuery, lang: str = "ru"):
    """
    Обновляет анализ лида (повторный запрос к AI).
    """
    await callback_request_ai(callback, lang)


## Callback выбора аккаунта
@router.callback_query(F.data.startswith("lead:select_account:"), OperatorFilter())
async def callback_select_account(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Обработка выбора аккаунта для отправки.
    """
    parts = callback.data.split(":")
    lead_id = int(parts[2])
    account_id = int(parts[3])

    await state.update_data(
        lead_id=lead_id,
        account_id=account_id
    )

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        account = await get_account_by_id(session, account_id)
        ai_data = lead.ai_data if lead else None

        if not lead or not account:
            await callback.answer(t("leads.data_error", lang), show_alert=True)
            return

        if ai_data and ai_data.reply_variants:
            try:
                variants = json.loads(ai_data.reply_variants)
                num_variants = len(variants) if isinstance(variants, list) else 3

                await callback.message.edit_text(
                    t("leads.account_selected", lang, label=account.label),
                    reply_markup=get_reply_variants_keyboard(lead_id, num_variants)
                )
            except:
                await callback.message.edit_text(
                    t("leads.account_selected_custom", lang, label=account.label),
                    reply_markup=None
                )
                await state.set_state(LeadStates.waiting_for_custom_text)
        else:
            await callback.message.edit_text(
                t("leads.account_selected_custom", lang, label=account.label),
                reply_markup=None
            )
            await state.set_state(LeadStates.waiting_for_custom_text)

    await callback.answer()


## Callback показа вариантов ответов
@router.callback_query(F.data.startswith("lead:show_replies:"), OperatorFilter())
async def callback_show_replies(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает варианты ответов от ИИ.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        ai_data = await get_lead_ai_data(session, lead_id)

        if not ai_data or not ai_data.reply_variants:
            await callback.answer(t("leads.no_variants", lang), show_alert=True)
            return

        try:
            variants = json.loads(ai_data.reply_variants)

            if not isinstance(variants, list) or len(variants) == 0:
                await callback.answer(t("leads.no_variants_short", lang), show_alert=True)
                return

            text_lines = [t("leads.variants_title", lang)]

            for i, variant in enumerate(variants[:3], 1):
                text_lines.append(f"<b>{t('leads.variant_n', lang, n=i)}:</b>")
                text_lines.append(variant[:300] + "..." if len(variant) > 300 else variant)
                text_lines.append("")

            text = "\n".join(text_lines)

            await callback.message.edit_text(
                text,
                reply_markup=get_reply_variants_keyboard(lead_id, len(variants[:3]))
            )

        except Exception as e:
            await callback.answer(f"❌ {str(e)[:50]}", show_alert=True)

    await callback.answer()


## Callback использования варианта ответа
@router.callback_query(F.data.startswith("lead:use_variant:"), OperatorFilter())
async def callback_use_variant(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Использует выбранный вариант ответа от ИИ.
    """
    parts = callback.data.split(":")
    lead_id = int(parts[2])
    variant_index = int(parts[3])

    data = await state.get_data()
    account_id = data.get("account_id")

    if not account_id:
        await callback.answer(t("leads.no_accounts", lang), show_alert=True)
        return

    async with get_session() as session:
        ai_data = await get_lead_ai_data(session, lead_id)
        account = await get_account_by_id(session, account_id)

        if not ai_data or not ai_data.reply_variants:
            await callback.answer(t("leads.no_variants_short", lang), show_alert=True)
            return

        try:
            variants = json.loads(ai_data.reply_variants)

            if variant_index >= len(variants):
                await callback.answer(t("leads.no_variants_short", lang), show_alert=True)
                return

            reply_text = variants[variant_index]

            await state.update_data(reply_text=reply_text)

            await callback.message.edit_text(
                f"📤 <b>{t('leads.sending', lang)}</b>\n\n"
                f"👤 <b>{account.label}</b>\n"
                f"📝\n\n"
                f"{reply_text}\n\n",
                reply_markup=get_send_confirmation_keyboard(lead_id, account_id, variant_index)
            )

        except Exception as e:
            await callback.answer(f"❌ {str(e)[:50]}", show_alert=True)

    await callback.answer()


## Callback "Свой текст"
@router.callback_query(F.data.startswith("lead:custom_text:"), OperatorFilter())
async def callback_custom_text(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Переводит в режим ожидания своего текста.
    """
    lead_id = int(callback.data.split(":")[2])

    await state.update_data(lead_id=lead_id)
    await state.set_state(LeadStates.waiting_for_custom_text)

    await callback.message.edit_text(
        t("leads.account_selected_custom", lang, label="..."),
    )
    await callback.answer()


## Обработка ввода своего текста
## Обработка своего текста (исключаем команды)
@router.message(LeadStates.waiting_for_custom_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_custom_text(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает введённый пользователем текст.
    """
    reply_text = message.text
    data = await state.get_data()
    lead_id = data.get("lead_id")
    account_id = data.get("account_id")

    if not lead_id:
        await message.answer(t("leads.edit_no_lead", lang))
        await state.clear()
        return

    if not account_id:
        async with get_session() as session:
            accounts = await get_all_accounts(session, enabled_only=True)

            if not accounts:
                await message.answer(t("leads.no_accounts", lang))
                await state.clear()
                return

            account_id = accounts[0].id
            account = accounts[0]
    else:
        async with get_session() as session:
            account = await get_account_by_id(session, account_id)

    await state.update_data(reply_text=reply_text, account_id=account_id)

    await message.answer(
        f"📤\n\n"
        f"👤 <b>{account.label}</b>\n"
        f"📝\n\n"
        f"{reply_text}",
        reply_markup=get_send_confirmation_keyboard(lead_id, account_id)
    )

    await state.clear()


## Callback быстрой отправки
@router.callback_query(F.data.startswith("lead:quick_send:"), OperatorFilter())
async def callback_quick_send(callback: CallbackQuery, lang: str = "ru"):
    """
    Быстрая отправка с настройками по умолчанию.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data if lead else None
        accounts = await get_all_accounts(session, enabled_only=True)

        if not accounts:
            await callback.answer(t("leads.no_accounts", lang), show_alert=True)
            return

        account = accounts[0]

        reply_text = None
        if ai_data and ai_data.reply_variants:
            try:
                variants = json.loads(ai_data.reply_variants)
                if isinstance(variants, list) and len(variants) > 0:
                    reply_text = variants[0]
            except:
                pass

        if not reply_text:
            await callback.answer(t("leads.no_variants", lang), show_alert=True)
            return

        success, _err = await send_message_via_listener(
            lead=lead,
            account=account,
            reply_text=reply_text,
            fast_mode=True
        )

        if success:
            await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)

            await create_reply(
                session,
                lead_id=lead_id,
                account_id=account.id,
                style_used=account.style_default,
                reply_text=reply_text,
                fast_mode_used=True,
                was_successful=True
            )

            await session.commit()

            await callback.message.edit_text(
                t("leads.sent_ok", lang, account=account.label),
                reply_markup=get_main_menu_keyboard(lang)
            )
            await callback.answer()
        else:
            await callback.answer(t("leads.send_error", lang), show_alert=True)


## Callback подтверждения отправки
@router.callback_query(F.data.startswith("lead:send_confirm:"), OperatorFilter())
async def callback_send_confirm(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Подтверждает и выполняет отправку сообщения.
    """
    parts = callback.data.split(":")
    lead_id = int(parts[2])
    account_id = int(parts[3])

    data = await state.get_data()
    reply_text = data.get("reply_text")

    if not reply_text:
        await callback.answer(t("leads.no_draft", lang), show_alert=True)
        return

    await callback.answer(t("leads.sending", lang), show_alert=False)

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        account = await get_account_by_id(session, account_id)

        if not lead or not account:
            await callback.answer(t("leads.data_error", lang), show_alert=True)
            return

        success, _err = await send_message_via_listener(
            lead=lead,
            account=account,
            reply_text=reply_text,
            fast_mode=False
        )

        if success:
            await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)

            await create_reply(
                session,
                lead_id=lead_id,
                account_id=account_id,
                style_used=account.style_default,
                reply_text=reply_text,
                fast_mode_used=False,
                was_successful=True
            )

            await session.commit()

            await callback.message.edit_text(
                t("leads.sent_ok", lang, account=account.label),
                reply_markup=get_main_menu_keyboard(lang)
            )
            await callback.answer()
        else:
            await callback.answer(t("leads.send_error", lang), show_alert=True)

    await state.clear()


## Callback редактирования текста
@router.callback_query(F.data.startswith("lead:edit_text:"), OperatorFilter())
async def callback_edit_text(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Переводит в режим редактирования текста.
    """
    lead_id = int(callback.data.split(":")[2])

    await state.update_data(lead_id=lead_id)
    await state.set_state(LeadStates.waiting_for_custom_text)

    await callback.message.edit_text(
        t("leads.edit_draft_title", lang) + t("leads.edit_prompt", lang)
    )
    await callback.answer()


## Callback игнорирования лида
@router.callback_query(F.data.startswith("lead:ignore:"), OperatorFilter())
async def callback_ignore_lead(callback: CallbackQuery, lang: str = "ru"):
    """
    Помечает лид как игнорированный и возвращает в список лидов.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await update_lead_status(session, lead_id, LeadStatus.IGNORED.value)
        await session.commit()

        if not success:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        start_date = datetime.utcnow() - timedelta(days=7)
        leads = await get_leads_by_date_range(
            session,
            start_date=start_date,
            limit=LEADS_PER_PAGE
        )

    await callback.answer("🚫", show_alert=False)

    if not leads:
        await callback.message.edit_text(
            t("leads.empty", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )
        return

    total_pages = max(1, (len(leads) + LEADS_PER_PAGE - 1) // LEADS_PER_PAGE)
    text = format_leads_list(leads[:LEADS_PER_PAGE], 0, total_pages)
    keyboard = get_leads_list_keyboard(leads[:LEADS_PER_PAGE], 0, total_pages)

    await callback.message.edit_text(text, reply_markup=keyboard)


## Callback навигации: следующий лид
@router.callback_query(F.data.startswith("lead:next:"), OperatorFilter())
async def callback_next_lead(callback: CallbackQuery, lang: str = "ru"):
    """
    Переход к следующему лиду.
    """
    current_lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        current_lead = await get_lead_by_id(session, current_lead_id)

        if not current_lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        from sqlalchemy import select
        from shared.database.models import Lead

        stmt = (
            select(Lead)
            .where(Lead.created_at > current_lead.created_at)
            .order_by(Lead.created_at.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        next_lead = result.scalar_one_or_none()

        if not next_lead:
            await callback.answer(t("leads.no_leads", lang), show_alert=True)
            return

        await _show_lead_card(callback, next_lead.id, lang=lang)


## Callback навигации: предыдущий лид
@router.callback_query(F.data.startswith("lead:prev:"), OperatorFilter())
async def callback_prev_lead(callback: CallbackQuery, lang: str = "ru"):
    """
    Переход к предыдущему лиду.
    """
    current_lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        current_lead = await get_lead_by_id(session, current_lead_id)

        if not current_lead:
            await callback.answer(t("leads.not_found", lang), show_alert=True)
            return

        from sqlalchemy import select
        from shared.database.models import Lead

        stmt = (
            select(Lead)
            .where(Lead.created_at < current_lead.created_at)
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        prev_lead = result.scalar_one_or_none()

        if not prev_lead:
            await callback.answer(t("leads.no_leads", lang), show_alert=True)
            return

        await _show_lead_card(callback, prev_lead.id, lang=lang)


## Обработка отмены во время работы с лидом
@router.message(Command("cancel"), LeadStates())
async def cancel_lead_action(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет текущее действие с лидом.
    """
    await state.clear()
    await message.answer(
        t("common.cancel", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )


## Обработка отмены во время редактирования черновика
@router.message(Command("cancel"), EditDraftStates())
async def cancel_edit_draft(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет редактирование черновика.
    """
    await state.clear()
    await message.answer(
        t("common.cancel", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )


## Вспомогательная функция отправки сообщения через Lead Listener
async def send_message_via_listener(
    lead,
    account,
    reply_text: str,
    fast_mode: bool = False
) -> tuple:
    """
    ## Отправляет сообщение через Lead Listener API (В ЛИЧКУ заказчику)
    """
    import httpx
    from config import settings

    logger.info(
        f"Отправка сообщения: "
        f"lead_id={lead.id}, "
        f"account={account.label}, "
        f"author=@{lead.author_username or 'N/A'} (id={lead.author_id}), "
        f"fast_mode={fast_mode}"
    )

    try:
        lead_listener_url = settings.admin_bot_api_url.replace('admin_bot', 'lead_listener').replace('8000', '8001')
        api_url = f"{lead_listener_url}/api/send_message"

        payload = {
            "lead_id": lead.id,
            "account_id": account.id,
            "chat_tg_id": lead.chat.tg_chat_id,
            "message_text": reply_text,
            "style_used": account.style_default,
            "reply_to_message_id": lead.message_id,
            "author_username": lead.author_username,
            "author_id": lead.author_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, json=payload)

            if response.status_code == 200:
                logger.info(f"Сообщение отправлено (lead #{lead.id})")
                return True, None

            try:
                error_code = response.json().get("error", "UNKNOWN")
            except Exception:
                error_code = "UNKNOWN"

            logger.error(
                f"Lead Listener ошибка: status={response.status_code}, error={error_code}"
            )
            return False, error_code

    except httpx.TimeoutException:
        logger.error(f"Timeout при отправке (lead #{lead.id})")
        return False, "TIMEOUT"

    except Exception as e:
        logger.exception(f"Непредвиденная ошибка при отправке: {e}")
        return False, "UNKNOWN"
