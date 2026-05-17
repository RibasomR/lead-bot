"""
## Хендлер генерации отклика на произвольный текст
Команда /gen — пользователь вставляет текст заказа, бот генерирует отклик.
"""

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import get_main_menu_keyboard
from admin_bot.states import GenerateReplyStates
from shared.ai.reply_generator import get_reply_generator
from shared.database.engine import get_session
from shared.database.crud import get_freelancer_profile

logger = logging.getLogger(__name__)

router = Router(name="generate_router")


def _gen_result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="gen:regen")],
        [InlineKeyboardButton(text="🔙 Готово", callback_data="gen:done")],
    ])


@router.message(Command("gen"), OperatorFilter())
async def cmd_generate(message: Message, state: FSMContext, lang: str = "ru"):
    await state.set_state(GenerateReplyStates.waiting_for_text)
    await message.answer(
        "✏️ <b>Генерация отклика</b>\n\n"
        "Вставь текст заказа (из чата, биржи и т.д.), и я сгенерирую отклик.\n\n"
        "/cancel для отмены."
    )


@router.message(Command("cancel"), GenerateReplyStates(), OperatorFilter())
async def cancel_generate(message: Message, state: FSMContext, lang: str = "ru"):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=get_main_menu_keyboard(lang))


@router.message(GenerateReplyStates.waiting_for_text, OperatorFilter(), ~F.text.startswith("/"))
async def process_generate_text(message: Message, state: FSMContext, lang: str = "ru"):
    lead_text = message.text.strip()
    if len(lead_text) < 10:
        await message.answer("⚠️ Слишком короткий текст. Вставь полный текст заказа.")
        return

    status_msg = await message.answer("⏳ Генерирую отклик…")

    async with get_session() as session:
        profile = await get_freelancer_profile(session)

    try:
        reply_gen = get_reply_generator()
        draft = await reply_gen.generate_reply(
            lead_text=lead_text,
            style="деловой",
            freelancer_profile=profile,
        )

        await state.update_data(lead_text=lead_text, last_draft=draft)
        await state.set_state(GenerateReplyStates.waiting_for_feedback)

        await status_msg.edit_text(
            f"📨 <b>Отклик:</b>\n\n{draft}\n\n"
            "💡 Нажми 🔄 для перегенерации или «Готово».",
            reply_markup=_gen_result_kb(),
        )

    except Exception as e:
        logger.error(f"Ошибка генерации отклика: {e}")
        await status_msg.edit_text(f"❌ Ошибка генерации: {str(e)[:100]}")
        await state.clear()


## Кнопка "Перегенерировать" — спрашиваем комментарий
@router.callback_query(F.data == "gen:regen", OperatorFilter())
async def callback_gen_regen(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    current_state = await state.get_state()
    if current_state != GenerateReplyStates.waiting_for_feedback.state:
        await callback.answer("❌ Нет активной генерации", show_alert=True)
        return

    await state.set_state(GenerateReplyStates.waiting_for_regen_comment)
    await callback.message.answer(
        "💬 Напиши комментарий, что изменить в отклике.\n"
        "Отправь <b>-</b> для перегенерации без комментария.\n"
        "/cancel для отмены."
    )
    await callback.answer()


## Получение комментария и перегенерация
@router.message(GenerateReplyStates.waiting_for_regen_comment, OperatorFilter(), ~F.text.startswith("/"))
async def process_regen_comment(message: Message, state: FSMContext, lang: str = "ru"):
    data = await state.get_data()
    lead_text = data.get("lead_text")
    previous_draft = data.get("last_draft")

    if not lead_text:
        await message.answer("❌ Текст заказа потерян. Начни заново: /gen")
        await state.clear()
        return

    feedback = message.text.strip()
    if feedback == "-":
        feedback = None

    status_msg = await message.answer("⏳ Перегенерация отклика…")

    async with get_session() as session:
        profile = await get_freelancer_profile(session)

    try:
        reply_gen = get_reply_generator()
        draft = await reply_gen.generate_reply(
            lead_text=lead_text,
            style="деловой",
            freelancer_profile=profile,
            feedback=feedback,
            previous_draft=previous_draft,
        )

        await state.update_data(last_draft=draft)
        await state.set_state(GenerateReplyStates.waiting_for_feedback)

        await status_msg.edit_text(
            f"📨 <b>Отклик:</b>\n\n{draft}\n\n"
            "💡 Нажми 🔄 для перегенерации или «Готово».",
            reply_markup=_gen_result_kb(),
        )

    except Exception as e:
        logger.error(f"Ошибка перегенерации: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


@router.callback_query(F.data == "gen:done", OperatorFilter())
async def callback_gen_done(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await state.clear()
    await callback.message.edit_text(
        callback.message.text or callback.message.html_text or "✅ Готово",
        reply_markup=None,
    )
    await callback.answer("✅")
