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
from shared.locales import t


router = Router(name="profile_router")


## Формирование текста профиля
def format_profile_text(profile, lang: str = "ru") -> str:
    """
    Форматирует профиль фрилансера для отображения.

    Args:
        profile: Объект FreelancerProfile или None
        lang: Код языка

    Returns:
        HTML-текст профиля
    """
    lines = [t("profile.title", lang), ""]

    if not profile:
        lines.append(hitalic(t("profile.empty", lang)))
        return "\n".join(lines)

    if profile.stack:
        lines.append(f"{t('profile.stack_label', lang)} {profile.stack}")
    else:
        lines.append(f"{t('profile.stack_label', lang)} {hitalic(t('profile.not_set', lang))}")

    if profile.specialization:
        lines.append(f"{t('profile.spec_label', lang)} {profile.specialization}")
    else:
        lines.append(f"{t('profile.spec_label', lang)} {hitalic(t('profile.not_set_f', lang))}")

    if profile.about:
        lines.append(f"{t('profile.about_label', lang)} {profile.about}")

    if profile.min_budget:
        lines.append(t("profile.budget_label", lang, amount=profile.min_budget))

    if profile.portfolio_url:
        lines.append(f"{t('profile.portfolio_label', lang)} {profile.portfolio_url}")

    lines.append("")
    lines.append(hitalic(t("profile.footer", lang)))

    return "\n".join(lines)


## Клавиатура профиля
def get_profile_keyboard(lang: str = "ru") -> "InlineKeyboardBuilder":
    """
    Клавиатура действий с профилем.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("profile.btn_stack", lang), callback_data="profile:edit:stack")
    builder.button(text=t("profile.btn_spec", lang), callback_data="profile:edit:specialization")
    builder.button(text=t("profile.btn_about", lang), callback_data="profile:edit:about")
    builder.button(text=t("profile.btn_budget", lang), callback_data="profile:edit:min_budget")
    builder.button(text=t("profile.btn_portfolio", lang), callback_data="profile:edit:portfolio")
    builder.button(text=t("profile.btn_back", lang), callback_data="menu:main")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


## Показ профиля (вызывается из start.py и напрямую)
async def show_profile(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает профиль фрилансера с кнопками редактирования.
    """
    async with get_session() as session:
        profile = await get_freelancer_profile(session)

    text = format_profile_text(profile, lang)
    await callback.message.edit_text(text, reply_markup=get_profile_keyboard(lang))
    await callback.answer()


## Маппинг полей → стейтов и ключей подсказок
FIELD_MAP = {
    "stack": {
        "state": ProfileStates.editing_stack,
        "prompt_key": "profile.prompt_stack",
        "field": "stack",
    },
    "specialization": {
        "state": ProfileStates.editing_specialization,
        "prompt_key": "profile.prompt_spec",
        "field": "specialization",
    },
    "about": {
        "state": ProfileStates.editing_about,
        "prompt_key": "profile.prompt_about",
        "field": "about",
    },
    "min_budget": {
        "state": ProfileStates.editing_min_budget,
        "prompt_key": "profile.prompt_budget",
        "field": "min_budget",
    },
    "portfolio": {
        "state": ProfileStates.editing_portfolio,
        "prompt_key": "profile.prompt_portfolio",
        "field": "portfolio_url",
    },
}


## Callback начала редактирования поля
@router.callback_query(F.data.startswith("profile:edit:"), OperatorFilter())
async def callback_edit_field(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Запускает FSM для редактирования конкретного поля профиля.
    """
    field_key = callback.data.split(":")[2]
    field_info = FIELD_MAP.get(field_key)

    if not field_info:
        await callback.answer(t("profile.unknown_field", lang), show_alert=True)
        return

    await state.update_data(editing_field=field_key)
    await state.set_state(field_info["state"])

    await callback.message.edit_text(
        t(field_info["prompt_key"], lang) + t("profile.cancel_prompt", lang)
    )
    await callback.answer()


## Обработка ввода: стек
@router.message(ProfileStates.editing_stack, OperatorFilter(), ~F.text.startswith("/"))
async def process_stack(message: Message, state: FSMContext, lang: str = "ru"):
    await _save_profile_field(message, state, "stack", message.text.strip(), lang)


## Обработка ввода: специализация
@router.message(ProfileStates.editing_specialization, OperatorFilter(), ~F.text.startswith("/"))
async def process_specialization(message: Message, state: FSMContext, lang: str = "ru"):
    await _save_profile_field(message, state, "specialization", message.text.strip(), lang)


## Обработка ввода: о себе
@router.message(ProfileStates.editing_about, OperatorFilter(), ~F.text.startswith("/"))
async def process_about(message: Message, state: FSMContext, lang: str = "ru"):
    await _save_profile_field(message, state, "about", message.text.strip(), lang)


## Обработка ввода: минимальный бюджет
@router.message(ProfileStates.editing_min_budget, OperatorFilter(), ~F.text.startswith("/"))
async def process_min_budget(message: Message, state: FSMContext, lang: str = "ru"):
    text = message.text.strip().replace(" ", "").replace(",", "").replace("₽", "").replace("руб", "")
    try:
        value = int(text)
        if value < 0:
            await message.answer(t("profile.budget_negative", lang))
            return
    except ValueError:
        await message.answer(t("profile.budget_invalid", lang))
        return
    await _save_profile_field(message, state, "min_budget", value, lang)


## Обработка ввода: портфолио
@router.message(ProfileStates.editing_portfolio, OperatorFilter(), ~F.text.startswith("/"))
async def process_portfolio(message: Message, state: FSMContext, lang: str = "ru"):
    await _save_profile_field(message, state, "portfolio_url", message.text.strip(), lang)


## Общая функция сохранения поля
async def _save_profile_field(message: Message, state: FSMContext, field: str, value, lang: str = "ru"):
    """
    Сохраняет значение поля в профиль и показывает обновлённый профиль.
    """
    async with get_session() as session:
        await create_or_update_freelancer_profile(session, **{field: value})
        await session.commit()
        profile = await get_freelancer_profile(session)

    await state.clear()

    text = f"{t('profile.saved', lang)}\n\n{format_profile_text(profile, lang)}"
    await message.answer(text, reply_markup=get_profile_keyboard(lang))


## Отмена редактирования профиля
@router.message(Command("cancel"), ProfileStates())
async def cancel_profile_edit(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет редактирование профиля.
    """
    await state.clear()
    await message.answer(
        t("profile.edit_cancelled", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )
