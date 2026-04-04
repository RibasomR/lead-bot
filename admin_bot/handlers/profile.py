"""
## Хендлеры профиля фрилансера (v2)
Просмотр и редактирование профиля для персонализации автоответов.
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold, hitalic, hcode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import get_main_menu_keyboard
from admin_bot.states import ProfileStates
from shared.database.engine import get_session
from shared.database.crud import get_freelancer_profile, create_or_update_freelancer_profile


router = Router(name="profile_router")


## Формирование текста профиля
def format_profile_text(profile) -> str:
    """
    Форматирует профиль фрилансера для отображения.

    Args:
        profile: Объект FreelancerProfile или None

    Returns:
        HTML-текст профиля
    """
    lines = [f"🧑‍💻 {hbold('Профиль фрилансера')}", ""]

    if not profile:
        lines.append(hitalic("Профиль не заполнен. Нажмите кнопку для редактирования."))
        return "\n".join(lines)

    if profile.stack:
        lines.append(f"🔧 {hbold('Стек:')} {profile.stack}")
    else:
        lines.append(f"🔧 {hbold('Стек:')} {hitalic('не указан')}")

    if profile.specialization:
        lines.append(f"🎯 {hbold('Специализация:')} {profile.specialization}")
    else:
        lines.append(f"🎯 {hbold('Специализация:')} {hitalic('не указана')}")

    if profile.about:
        lines.append(f"📝 {hbold('О себе:')} {profile.about}")

    if profile.min_budget:
        lines.append(f"💰 {hbold('Мин. бюджет:')} {profile.min_budget:,} ₽")

    if profile.portfolio_url:
        lines.append(f"🔗 {hbold('Портфолио:')} {profile.portfolio_url}")

    lines.append("")
    lines.append(hitalic("Профиль используется для генерации персональных автоответов."))

    return "\n".join(lines)


## Клавиатура профиля
def get_profile_keyboard() -> "InlineKeyboardBuilder":
    """
    Клавиатура действий с профилем.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="🔧 Стек", callback_data="profile:edit:stack")
    builder.button(text="🎯 Специализация", callback_data="profile:edit:specialization")
    builder.button(text="📝 О себе", callback_data="profile:edit:about")
    builder.button(text="💰 Мин. бюджет", callback_data="profile:edit:min_budget")
    builder.button(text="🔗 Портфолио", callback_data="profile:edit:portfolio")
    builder.button(text="🔙 В меню", callback_data="menu:main")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


## Показ профиля (вызывается из start.py и напрямую)
async def show_profile(callback: CallbackQuery):
    """
    Показывает профиль фрилансера с кнопками редактирования.
    """
    async with get_session() as session:
        profile = await get_freelancer_profile(session)

    text = format_profile_text(profile)
    await callback.message.edit_text(text, reply_markup=get_profile_keyboard())
    await callback.answer()


## Маппинг полей → стейтов и подсказок
FIELD_MAP = {
    "stack": {
        "state": ProfileStates.editing_stack,
        "prompt": "🔧 Введите стек технологий (через запятую):\n\nПример: Python, aiogram, Telethon, Next.js, PostgreSQL, Docker",
        "field": "stack",
    },
    "specialization": {
        "state": ProfileStates.editing_specialization,
        "prompt": "🎯 Введите специализацию:\n\nПример: Telegram боты, веб-приложения, автоматизация, AI-интеграции",
        "field": "specialization",
    },
    "about": {
        "state": ProfileStates.editing_about,
        "prompt": "📝 Расскажите о себе (1-3 предложения):\n\nЭтот текст будет использоваться при генерации автоответов.",
        "field": "about",
    },
    "min_budget": {
        "state": ProfileStates.editing_min_budget,
        "prompt": "💰 Введите минимальный бюджет проекта (число в рублях):\n\nПример: 15000",
        "field": "min_budget",
    },
    "portfolio": {
        "state": ProfileStates.editing_portfolio,
        "prompt": "🔗 Введите ссылку на портфолио:\n\nПример: https://github.com/username",
        "field": "portfolio_url",
    },
}


## Callback начала редактирования поля
@router.callback_query(F.data.startswith("profile:edit:"), OperatorFilter())
async def callback_edit_field(callback: CallbackQuery, state: FSMContext):
    """
    Запускает FSM для редактирования конкретного поля профиля.
    """
    field_key = callback.data.split(":")[2]
    field_info = FIELD_MAP.get(field_key)

    if not field_info:
        await callback.answer("❌ Неизвестное поле", show_alert=True)
        return

    await state.update_data(editing_field=field_key)
    await state.set_state(field_info["state"])

    await callback.message.edit_text(
        f"{field_info['prompt']}\n\nОтправьте /cancel для отмены."
    )
    await callback.answer()


## Обработка ввода: стек
@router.message(ProfileStates.editing_stack, OperatorFilter(), ~F.text.startswith("/"))
async def process_stack(message: Message, state: FSMContext):
    await _save_profile_field(message, state, "stack", message.text.strip())


## Обработка ввода: специализация
@router.message(ProfileStates.editing_specialization, OperatorFilter(), ~F.text.startswith("/"))
async def process_specialization(message: Message, state: FSMContext):
    await _save_profile_field(message, state, "specialization", message.text.strip())


## Обработка ввода: о себе
@router.message(ProfileStates.editing_about, OperatorFilter(), ~F.text.startswith("/"))
async def process_about(message: Message, state: FSMContext):
    await _save_profile_field(message, state, "about", message.text.strip())


## Обработка ввода: минимальный бюджет
@router.message(ProfileStates.editing_min_budget, OperatorFilter(), ~F.text.startswith("/"))
async def process_min_budget(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "").replace(",", "").replace("₽", "").replace("руб", "")
    try:
        value = int(text)
        if value < 0:
            await message.answer("❌ Бюджет не может быть отрицательным. Попробуйте ещё раз.")
            return
    except ValueError:
        await message.answer("❌ Введите число. Например: 15000")
        return
    await _save_profile_field(message, state, "min_budget", value)


## Обработка ввода: портфолио
@router.message(ProfileStates.editing_portfolio, OperatorFilter(), ~F.text.startswith("/"))
async def process_portfolio(message: Message, state: FSMContext):
    await _save_profile_field(message, state, "portfolio_url", message.text.strip())


## Общая функция сохранения поля
async def _save_profile_field(message: Message, state: FSMContext, field: str, value):
    """
    Сохраняет значение поля в профиль и показывает обновлённый профиль.
    """
    async with get_session() as session:
        await create_or_update_freelancer_profile(session, **{field: value})
        await session.commit()
        profile = await get_freelancer_profile(session)

    await state.clear()

    text = f"✅ Сохранено!\n\n{format_profile_text(profile)}"
    await message.answer(text, reply_markup=get_profile_keyboard())


## Отмена редактирования профиля
@router.message(Command("cancel"), ProfileStates())
async def cancel_profile_edit(message: Message, state: FSMContext):
    """
    Отменяет редактирование профиля.
    """
    await state.clear()
    await message.answer(
        "❌ Редактирование отменено.",
        reply_markup=get_main_menu_keyboard()
    )
