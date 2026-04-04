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
from config import settings

import logging
logger = logging.getLogger(__name__)


router = Router(name="leads_router")

# Константы
LEADS_PER_PAGE = 8


## Команда /leads
@router.message(Command("leads"), OperatorFilter())
async def cmd_leads(message: Message):
    """
    Показывает список всех лидов (кроме ignored) с пагинацией.
    """
    await _show_leads_page(message, page=0, edit=False)


async def _show_leads_page(message_or_callback, page: int, edit: bool = True):
    """Общая логика отображения страницы лидов."""
    from shared.database.crud import get_all_leads

    async with get_session() as session:
        all_leads = await get_all_leads(session, limit=1000)

    if not all_leads:
        text = "📭 <b>Лидов не найдено</b>"
        kb = get_main_menu_keyboard()
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
async def callback_leads_menu(callback: CallbackQuery):
    """
    Обработчик callback меню лидов.
    """
    await _show_leads_page(callback, page=0)
    await callback.answer()


## Callback пагинации лидов
@router.callback_query(F.data.startswith("leads:page:"), OperatorFilter())
async def callback_leads_page(callback: CallbackQuery):
    """
    Обработчик перехода по страницам лидов.
    """
    try:
        page = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка навигации")
        return

    await _show_leads_page(callback, page=page)
    await callback.answer()


## Callback просмотра конкретного лида
@router.callback_query(F.data.startswith("lead:show:"), OperatorFilter())
async def callback_show_lead(callback: CallbackQuery):
    """
    Показывает подробную карточку лида.
    Автоматически обновляет статус на 'viewed'.
    """
    lead_id = int(callback.data.split(":")[2])
    await _show_lead_card(callback, lead_id)


async def _show_lead_card(callback: CallbackQuery, lead_id: int):
    """Общая логика показа карточки лида (используется в show/prev/next)."""
    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)

        if not lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
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
async def callback_send_draft(callback: CallbackQuery, state: FSMContext):
    """
    Отправить черновик ответа сразу. Автовыбор аккаунта с ролью reply/both.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return

        ai_data = lead.ai_data
        draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

        if not draft:
            await callback.answer("❌ Нет черновика для отправки", show_alert=True)
            return

        accounts = await get_all_accounts(session, enabled_only=True)
        if not accounts:
            await callback.answer("❌ Нет доступных аккаунтов", show_alert=True)
            return

        ## Автовыбор аккаунта: reply > both > первый доступный
        account = next(
            (a for a in accounts if a.role == "reply"),
            next(
                (a for a in accounts if a.role == "both"),
                accounts[0]
            )
        )

        await callback.answer("⏳ Отправка...", show_alert=False)

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
                f"✅ {hbold('Сообщение отправлено!')}\n\n"
                f"👤 Аккаунт: {account.label}\n"
                f"📝 Текст отправлен в ЛС.",
                reply_markup=get_main_menu_keyboard()
            )
        elif error_code == "NO_DM_ACCESS":
            ## Не удалось отправить в ЛС — показываем ссылку и черновик для ручной отправки
            chat_title = lead.chat.title if lead.chat else "Неизвестный чат"
            lines = [f"⚠️ {hbold('Не удалось отправить в ЛС')}"]
            lines.append("У автора нет username / аккаунт не может связаться.\n")
            lines.append(f"💬 Чат: {chat_title}")

            if lead.message_url:
                lines.append(f"🔗 <a href=\"{lead.message_url}\">Перейти к сообщению</a>")

            lines.append(f"\n📋 {hbold('Черновик для копирования:')}")
            lines.append(f"<pre>{draft}</pre>")

            ## Кнопка «Отправил вручную» — помечает лид как replied
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ Отправил вручную",
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
                f"❌ {hbold('Ошибка при отправке')}\n\n"
                f"Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )

    await state.clear()


## Callback «Отправил вручную» — помечает лид как replied
@router.callback_query(F.data.startswith("lead:mark_replied:"), OperatorFilter())
async def callback_mark_replied(callback: CallbackQuery):
    """Оператор отправил сообщение вручную — помечаем лид как replied."""
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)
        await session.commit()

    await callback.message.edit_text(
        f"✅ Лид #{lead_id} помечен как «Отвечено».",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


## Callback редактирования черновика (v2)
@router.callback_query(F.data.startswith("lead:edit_draft:"), OperatorFilter())
async def callback_edit_draft(callback: CallbackQuery, state: FSMContext):
    """
    Переводит в FSM для редактирования текста черновика.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return

        ai_data = lead.ai_data
        draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

    await state.update_data(lead_id=lead_id)
    await state.set_state(EditDraftStates.waiting_for_edited_text)

    text = f"✏️ {hbold('Редактирование черновика')}\n\n"
    if draft:
        text += f"📝 Текущий текст:\n{draft}\n\n"
    text += "Отправьте новый текст или /cancel для отмены."

    await callback.message.edit_text(text)
    await callback.answer()


## Обработка отредактированного текста черновика (v2)
@router.message(EditDraftStates.waiting_for_edited_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_edited_draft(message: Message, state: FSMContext):
    """
    Сохраняет отредактированный черновик и показывает обновлённую карточку.
    """
    data = await state.get_data()
    lead_id = data.get("lead_id")

    if not lead_id:
        await message.answer("❌ Ошибка: лид не выбран")
        await state.clear()
        return

    new_text = message.text.strip()

    async with get_session() as session:
        await update_lead(session, lead_id, draft_reply=new_text)
        await session.commit()

        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data

        text = format_lead_card(lead, ai_data)
        keyboard = get_lead_card_keyboard(
            lead_id, has_draft=True, has_ai_data=ai_data is not None
        )

    await state.clear()
    await message.answer(f"✅ Черновик обновлён\n\n{text}", reply_markup=keyboard)


## Callback перегенерации черновика — спрашиваем комментарий
@router.callback_query(F.data.startswith("lead:regenerate:"), OperatorFilter())
async def callback_regenerate_draft(callback: CallbackQuery, state: FSMContext):
    """
    Спрашивает комментарий оператора перед перегенерацией черновика.
    Если черновика ещё нет — генерирует сразу без вопросов.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return

        ## Если черновика ещё нет — генерируем сразу
        current_draft = lead.draft_reply or (lead.ai_data.generated_reply if lead.ai_data else None)
        if not current_draft:
            await callback.answer("⏳ Генерация черновика…")
            await _do_regenerate(callback, session, lead, feedback=None)
            return

    ## Черновик есть — спрашиваем фидбек
    await state.set_state(RegenerateDraftStates.waiting_for_feedback)
    await state.update_data(regenerate_lead_id=lead_id)
    await callback.message.answer(
        "✏️ Напиши, что не устроило в черновике, и я учту это при перегенерации.\n\n"
        "Или отправь <b>-</b> чтобы перегенерировать без комментария.\n"
        "Отправь /cancel для отмены.",
    )
    await callback.answer()


## Обработка отмены во время перегенерации черновика
@router.message(Command("cancel"), RegenerateDraftStates.waiting_for_feedback, OperatorFilter())
async def cancel_regenerate_draft(message: Message, state: FSMContext):
    """
    Отменяет перегенерацию черновика по /cancel.
    """
    await state.clear()
    await message.answer(
        "❌ Перегенерация отменена.",
        reply_markup=get_main_menu_keyboard()
    )


## Обработка комментария оператора для перегенерации
@router.message(RegenerateDraftStates.waiting_for_feedback, OperatorFilter())
async def handle_regenerate_feedback(message: Message, state: FSMContext):
    """
    Получает комментарий оператора и перегенерирует черновик с его учётом.
    """
    ## Если оператор отправил команду (не "-") — отменяем перегенерацию
    if message.text and message.text.startswith("/") and message.text.strip() != "-":
        await state.clear()
        await message.answer("❌ Перегенерация отменена.")
        return

    data = await state.get_data()
    lead_id = data.get("regenerate_lead_id")
    await state.clear()

    if not lead_id:
        await message.answer("❌ Лид не найден. Попробуйте снова.")
        return

    feedback = message.text.strip() if message.text else None
    if feedback == "-":
        feedback = None

    status_msg = await message.answer("⏳ Перегенерация черновика…")

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await status_msg.edit_text("❌ Лид не найден.")
            return

        await _do_regenerate_with_message(status_msg, session, lead, feedback=feedback)


async def _do_regenerate(
    callback: CallbackQuery, session, lead, feedback: Optional[str] = None
):
    """Общая логика перегенерации черновика (из callback)."""
    lead_id = lead.id
    ai_data = lead.ai_data

    ## Определяем стиль: из AI-рекомендации или дефолтный
    style = "деловой"
    if ai_data and ai_data.tone_recommendation:
        style = ai_data.tone_recommendation

    ## Получаем профиль фрилансера
    profile = await get_freelancer_profile(session)

    ## Предыдущий черновик для контекста
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

        ## Сохраняем в lead.draft_reply
        await update_lead(session, lead_id, draft_reply=draft)

        ## Также обновляем generated_reply в ai_data если есть
        if ai_data:
            await update_lead_ai_data(session, lead_id, generated_reply=draft)

        await session.commit()

        ## Перезагружаем и показываем обновлённую карточку
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data

        text = format_lead_card(lead, ai_data)
        keyboard = get_lead_card_keyboard(
            lead_id, has_draft=True, has_ai_data=ai_data is not None
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка генерации черновика для лида #{lead_id}: {e}")
        await callback.answer(
            f"❌ Ошибка генерации: {str(e)[:80]}",
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
        logger.error(f"❌ Ошибка генерации черновика для лида #{lead_id}: {e}")
        await status_msg.edit_text(f"❌ Ошибка генерации: {str(e)[:80]}")


## Callback добавления автора в ЧС (v2)
@router.callback_query(F.data.startswith("lead:blacklist_author:"), OperatorFilter())
async def callback_blacklist_author(callback: CallbackQuery):
    """
    Помечает автора лида в чёрный список (игнорируем все его сообщения).
    Реализовано как ignore лида + лог предупреждения (полноценный blacklist — фаза 7).
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        if not lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return

        author_info = lead.author_username or lead.author_name or str(lead.author_id)

        ## Помечаем лид как ignored
        await update_lead_status(session, lead_id, LeadStatus.IGNORED.value)
        await session.commit()

        logger.info(f"🚫 Автор '{author_info}' добавлен в ЧС (лид #{lead_id})")

    await callback.message.edit_text(
        f"🚫 {hbold('Автор добавлен в ЧС')}\n\n"
        f"👤 {author_info}\n"
        f"Лид #{lead_id} помечен как игнорированный.\n\n"
        f"⚠️ Полноценная фильтрация по автору будет в следующей версии.",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer("🚫 Автор в ЧС")


## Callback запроса анализа ИИ
@router.callback_query(F.data.startswith("lead:request_ai:"), OperatorFilter())
async def callback_request_ai(callback: CallbackQuery):
    """
    Запрашивает анализ лида у AI Advisor.
    """
    lead_id = int(callback.data.split(":")[2])
    
    await callback.answer("⏳ Запрос к ИИ...", show_alert=False)
    
    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        
        if not lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return
        
        # Проверяем, нет ли уже AI данных
        existing_ai_data = await get_lead_ai_data(session, lead_id)
        
        try:
            # Инициализируем AI Advisor
            ai_advisor = AIAdvisor(
                api_key=settings.openrouter_api_key,
                primary_model=settings.ai_model_primary,
                secondary_model=settings.ai_model_secondary
            )
            
            # Запрашиваем анализ лида
            analysis = await ai_advisor.score_lead(lead.message_text)
            
            # Сохраняем или обновляем AI данные
            if existing_ai_data:
                # Обновляем существующие данные
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
                # Создаём новые данные
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
            
            # Перезагружаем лид с новыми AI данными
            lead = await get_lead_by_id(session, lead_id, load_relations=True)
            ai_data = lead.ai_data
            draft = lead.draft_reply or (ai_data.generated_reply if ai_data else None)

            # Обновляем карточку
            text = format_lead_card(lead, ai_data)
            keyboard = get_lead_card_keyboard(
                lead_id, has_draft=bool(draft), has_ai_data=ai_data is not None
            )
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer("✅ Анализ получен", show_alert=False)
            
        except Exception as e:
            await callback.answer(
                f"❌ Ошибка при запросе к ИИ: {str(e)[:100]}",
                show_alert=True
            )


## Callback обновления анализа ИИ
@router.callback_query(F.data.startswith("lead:refresh_ai:"), OperatorFilter())
async def callback_refresh_ai(callback: CallbackQuery):
    """
    Обновляет анализ лида (повторный запрос к AI).
    """
    # Переиспользуем логику запроса
    await callback_request_ai(callback)


## Callback выбора аккаунта
@router.callback_query(F.data.startswith("lead:select_account:"), OperatorFilter())
async def callback_select_account(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора аккаунта для отправки.
    Сохраняет выбор и предлагает варианты ответов.
    """
    parts = callback.data.split(":")
    lead_id = int(parts[2])
    account_id = int(parts[3])
    
    # Сохраняем выбор в state
    await state.update_data(
        lead_id=lead_id,
        account_id=account_id
    )
    
    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        account = await get_account_by_id(session, account_id)
        ai_data = lead.ai_data if lead else None
        
        if not lead or not account:
            await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
            return
        
        # Если есть AI данные с вариантами ответов, показываем их
        if ai_data and ai_data.reply_variants:
            try:
                variants = json.loads(ai_data.reply_variants)
                num_variants = len(variants) if isinstance(variants, list) else 3
                
                await callback.message.edit_text(
                    f"✅ <b>Выбран аккаунт:</b> {account.label}\n\n"
                    f"💬 Выберите вариант ответа или введите свой текст:",
                    reply_markup=get_reply_variants_keyboard(lead_id, num_variants)
                )
            except:
                # Если не удалось распарсить варианты
                await callback.message.edit_text(
                    f"✅ <b>Выбран аккаунт:</b> {account.label}\n\n"
                    f"✏️ Введите текст сообщения для отправки:",
                    reply_markup=None
                )
                await state.set_state(LeadStates.waiting_for_custom_text)
        else:
            # Нет вариантов от ИИ — просим ввести свой текст
            await callback.message.edit_text(
                f"✅ <b>Выбран аккаунт:</b> {account.label}\n\n"
                f"✏️ Введите текст сообщения для отправки:\n\n"
                f"Отправьте /cancel для отмены.",
                reply_markup=None
            )
            await state.set_state(LeadStates.waiting_for_custom_text)
    
    await callback.answer()


## Callback показа вариантов ответов
@router.callback_query(F.data.startswith("lead:show_replies:"), OperatorFilter())
async def callback_show_replies(callback: CallbackQuery):
    """
    Показывает варианты ответов от ИИ.
    """
    lead_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        ai_data = await get_lead_ai_data(session, lead_id)
        
        if not ai_data or not ai_data.reply_variants:
            await callback.answer(
                "❌ Нет вариантов ответов. Запросите анализ ИИ.",
                show_alert=True
            )
            return
        
        try:
            variants = json.loads(ai_data.reply_variants)
            
            if not isinstance(variants, list) or len(variants) == 0:
                await callback.answer("❌ Нет вариантов ответов", show_alert=True)
                return
            
            # Формируем текст с вариантами
            text_lines = ["💬 <b>Варианты ответов от ИИ:</b>\n"]
            
            for i, variant in enumerate(variants[:3], 1):
                text_lines.append(f"<b>Вариант {i}:</b>")
                text_lines.append(variant[:300] + "..." if len(variant) > 300 else variant)
                text_lines.append("")
            
            text = "\n".join(text_lines)
            
            await callback.message.edit_text(
                text,
                reply_markup=get_reply_variants_keyboard(lead_id, len(variants[:3]))
            )
            
        except Exception as e:
            await callback.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
    
    await callback.answer()


## Callback использования варианта ответа
@router.callback_query(F.data.startswith("lead:use_variant:"), OperatorFilter())
async def callback_use_variant(callback: CallbackQuery, state: FSMContext):
    """
    Использует выбранный вариант ответа от ИИ.
    """
    parts = callback.data.split(":")
    lead_id = int(parts[2])
    variant_index = int(parts[3])
    
    # Получаем выбранный аккаунт из state
    data = await state.get_data()
    account_id = data.get("account_id")
    
    if not account_id:
        await callback.answer(
            "❌ Сначала выберите аккаунт для отправки",
            show_alert=True
        )
        return
    
    async with get_session() as session:
        ai_data = await get_lead_ai_data(session, lead_id)
        account = await get_account_by_id(session, account_id)
        
        if not ai_data or not ai_data.reply_variants:
            await callback.answer("❌ Нет вариантов ответов", show_alert=True)
            return
        
        try:
            variants = json.loads(ai_data.reply_variants)
            
            if variant_index >= len(variants):
                await callback.answer("❌ Вариант не найден", show_alert=True)
                return
            
            reply_text = variants[variant_index]
            
            # Сохраняем текст в state
            await state.update_data(reply_text=reply_text)
            
            # Показываем подтверждение
            await callback.message.edit_text(
                f"📤 <b>Отправка ответа</b>\n\n"
                f"👤 <b>Аккаунт:</b> {account.label}\n"
                f"📝 <b>Текст:</b>\n\n"
                f"{reply_text}\n\n"
                f"Подтвердите отправку:",
                reply_markup=get_send_confirmation_keyboard(lead_id, account_id, variant_index)
            )
            
        except Exception as e:
            await callback.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
    
    await callback.answer()


## Callback "Свой текст"
@router.callback_query(F.data.startswith("lead:custom_text:"), OperatorFilter())
async def callback_custom_text(callback: CallbackQuery, state: FSMContext):
    """
    Переводит в режим ожидания своего текста.
    """
    lead_id = int(callback.data.split(":")[2])
    
    await state.update_data(lead_id=lead_id)
    await state.set_state(LeadStates.waiting_for_custom_text)
    
    await callback.message.edit_text(
        "✏️ <b>Ввод своего текста</b>\n\n"
        "Отправьте текст сообщения, которое хотите отправить.\n\n"
        "Отправьте /cancel для отмены."
    )
    await callback.answer()


## Обработка ввода своего текста
## Обработка своего текста (исключаем команды)
@router.message(LeadStates.waiting_for_custom_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_custom_text(message: Message, state: FSMContext):
    """
    Обрабатывает введённый пользователем текст.
    """
    reply_text = message.text
    data = await state.get_data()
    lead_id = data.get("lead_id")
    account_id = data.get("account_id")
    
    if not lead_id:
        await message.answer("❌ Ошибка: лид не выбран")
        await state.clear()
        return
    
    if not account_id:
        # Если аккаунт не выбран, просим выбрать
        async with get_session() as session:
            accounts = await get_all_accounts(session, enabled_only=True)
            
            if not accounts:
                await message.answer(
                    "❌ Нет доступных аккаунтов.\n"
                    "Добавьте и активируйте хотя бы один аккаунт."
                )
                await state.clear()
                return
            
            # Используем первый доступный аккаунт
            account_id = accounts[0].id
            account = accounts[0]
    else:
        async with get_session() as session:
            account = await get_account_by_id(session, account_id)
    
    # Сохраняем текст в state
    await state.update_data(reply_text=reply_text, account_id=account_id)
    
    # Показываем подтверждение
    await message.answer(
        f"📤 <b>Отправка ответа</b>\n\n"
        f"👤 <b>Аккаунт:</b> {account.label}\n"
        f"📝 <b>Текст:</b>\n\n"
        f"{reply_text}\n\n"
        f"Подтвердите отправку:",
        reply_markup=get_send_confirmation_keyboard(lead_id, account_id)
    )
    
    await state.clear()


## Callback быстрой отправки
@router.callback_query(F.data.startswith("lead:quick_send:"), OperatorFilter())
async def callback_quick_send(callback: CallbackQuery):
    """
    Быстрая отправка с настройками по умолчанию.
    Использует первый доступный аккаунт и первый вариант ответа от ИИ.
    """
    lead_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        ai_data = lead.ai_data if lead else None
        accounts = await get_all_accounts(session, enabled_only=True)
        
        if not accounts:
            await callback.answer(
                "❌ Нет доступных аккаунтов",
                show_alert=True
            )
            return
        
        account = accounts[0]
        
        # Пытаемся взять первый вариант от ИИ
        reply_text = None
        if ai_data and ai_data.reply_variants:
            try:
                variants = json.loads(ai_data.reply_variants)
                if isinstance(variants, list) and len(variants) > 0:
                    reply_text = variants[0]
            except:
                pass
        
        if not reply_text:
            await callback.answer(
                "❌ Нет вариантов ответа. Используйте 'Свой текст'",
                show_alert=True
            )
            return
        
        # Отправляем сразу
        success, _err = await send_message_via_listener(
            lead=lead,
            account=account,
            reply_text=reply_text,
            fast_mode=True
        )

        if success:
            # Обновляем статус
            await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)
            
            # Создаём запись об ответе
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
                f"✅ <b>Сообщение отправлено!</b>\n\n"
                f"👤 Аккаунт: {account.label}\n"
                f"⚡ Режим: Быстрая отправка\n\n"
                f"Ответ успешно отправлен в чат.",
                reply_markup=get_main_menu_keyboard()
            )
            await callback.answer("✅ Отправлено", show_alert=False)
        else:
            await callback.answer(
                "❌ Ошибка при отправке сообщения",
                show_alert=True
            )


## Callback подтверждения отправки
@router.callback_query(F.data.startswith("lead:send_confirm:"), OperatorFilter())
async def callback_send_confirm(callback: CallbackQuery, state: FSMContext):
    """
    Подтверждает и выполняет отправку сообщения.
    """
    parts = callback.data.split(":")
    lead_id = int(parts[2])
    account_id = int(parts[3])
    
    # Получаем текст из state
    data = await state.get_data()
    reply_text = data.get("reply_text")
    
    if not reply_text:
        await callback.answer("❌ Текст сообщения не найден", show_alert=True)
        return
    
    await callback.answer("⏳ Отправка...", show_alert=False)
    
    async with get_session() as session:
        lead = await get_lead_by_id(session, lead_id, load_relations=True)
        account = await get_account_by_id(session, account_id)
        
        if not lead or not account:
            await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
            return
        
        # Отправляем сообщение
        success, _err = await send_message_via_listener(
            lead=lead,
            account=account,
            reply_text=reply_text,
            fast_mode=False
        )

        if success:
            # Обновляем статус
            await update_lead_status(session, lead_id, LeadStatus.REPLIED.value)
            
            # Создаём запись об ответе
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
                f"✅ <b>Сообщение отправлено!</b>\n\n"
                f"👤 Аккаунт: {account.label}\n"
                f"📝 Текст отправлен в чат.\n\n"
                f"Статус лида изменён на 'Отвечено'.",
                reply_markup=get_main_menu_keyboard()
            )
            await callback.answer("✅ Успешно отправлено", show_alert=False)
        else:
            await callback.answer(
                "❌ Ошибка при отправке. Попробуйте позже.",
                show_alert=True
            )
    
    await state.clear()


## Callback редактирования текста
@router.callback_query(F.data.startswith("lead:edit_text:"), OperatorFilter())
async def callback_edit_text(callback: CallbackQuery, state: FSMContext):
    """
    Переводит в режим редактирования текста.
    """
    lead_id = int(callback.data.split(":")[2])
    
    await state.update_data(lead_id=lead_id)
    await state.set_state(LeadStates.waiting_for_custom_text)
    
    await callback.message.edit_text(
        "✏️ <b>Редактирование текста</b>\n\n"
        "Отправьте новый текст сообщения.\n\n"
        "Отправьте /cancel для отмены."
    )
    await callback.answer()


## Callback игнорирования лида
@router.callback_query(F.data.startswith("lead:ignore:"), OperatorFilter())
async def callback_ignore_lead(callback: CallbackQuery):
    """
    Помечает лид как игнорированный и возвращает в список лидов.
    """
    lead_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await update_lead_status(session, lead_id, LeadStatus.IGNORED.value)
        await session.commit()

        if not success:
            await callback.answer("❌ Ошибка при обновлении статуса", show_alert=True)
            return

        ## Возвращаем в список лидов
        start_date = datetime.utcnow() - timedelta(days=7)
        leads = await get_leads_by_date_range(
            session,
            start_date=start_date,
            limit=LEADS_PER_PAGE
        )

    await callback.answer("🚫 Лид игнорирован", show_alert=False)

    if not leads:
        await callback.message.edit_text(
            "📭 <b>Лидов не найдено</b>\n\n"
            "Пока нет новых лидов за последнюю неделю.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    total_pages = max(1, (len(leads) + LEADS_PER_PAGE - 1) // LEADS_PER_PAGE)
    text = format_leads_list(leads[:LEADS_PER_PAGE], 0, total_pages)
    keyboard = get_leads_list_keyboard(leads[:LEADS_PER_PAGE], 0, total_pages)

    await callback.message.edit_text(text, reply_markup=keyboard)


## Callback навигации: следующий лид
@router.callback_query(F.data.startswith("lead:next:"), OperatorFilter())
async def callback_next_lead(callback: CallbackQuery):
    """
    Переход к следующему лиду.
    """
    current_lead_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        # Получаем все лиды после текущего
        current_lead = await get_lead_by_id(session, current_lead_id)
        
        if not current_lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return
        
        # Ищем следующий лид (созданный позже)
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
            await callback.answer("📭 Это последний лид", show_alert=True)
            return
        
        await _show_lead_card(callback, next_lead.id)


## Callback навигации: предыдущий лид
@router.callback_query(F.data.startswith("lead:prev:"), OperatorFilter())
async def callback_prev_lead(callback: CallbackQuery):
    """
    Переход к предыдущему лиду.
    """
    current_lead_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        # Получаем текущий лид
        current_lead = await get_lead_by_id(session, current_lead_id)
        
        if not current_lead:
            await callback.answer("❌ Лид не найден", show_alert=True)
            return
        
        # Ищем предыдущий лид (созданный раньше)
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
            await callback.answer("📭 Это первый лид", show_alert=True)
            return
        
        await _show_lead_card(callback, prev_lead.id)


## Обработка отмены во время работы с лидом
@router.message(Command("cancel"), LeadStates())
async def cancel_lead_action(message: Message, state: FSMContext):
    """
    Отменяет текущее действие с лидом.
    """
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_menu_keyboard()
    )


## Обработка отмены во время редактирования черновика
@router.message(Command("cancel"), EditDraftStates())
async def cancel_edit_draft(message: Message, state: FSMContext):
    """
    Отменяет редактирование черновика.
    """
    await state.clear()
    await message.answer(
        "❌ Редактирование отменено.",
        reply_markup=get_main_menu_keyboard()
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

    Args:
        lead: Объект лида
        account: Объект аккаунта
        reply_text: Текст для отправки
        fast_mode: Режим быстрой отправки

    Returns:
        (success: bool, error_code: str | None)
    """
    import httpx
    from config import settings

    logger.info(
        f"📤 Отправка сообщения: "
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

        logger.debug(f"🔗 API URL: {api_url}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, json=payload)

            if response.status_code == 200:
                logger.info(f"✅ Сообщение отправлено (lead #{lead.id})")
                return True, None

            ## Парсим error code из ответа
            try:
                error_code = response.json().get("error", "UNKNOWN")
            except Exception:
                error_code = "UNKNOWN"

            logger.error(
                f"❌ Lead Listener ошибка: status={response.status_code}, error={error_code}"
            )
            return False, error_code

    except httpx.TimeoutException:
        logger.error(f"❌ Timeout при отправке (lead #{lead.id})")
        return False, "TIMEOUT"

    except Exception as e:
        logger.exception(f"❌ Непредвиденная ошибка при отправке: {e}")
        return False, "UNKNOWN"

