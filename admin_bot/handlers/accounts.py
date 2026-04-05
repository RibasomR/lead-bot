"""
## Хендлеры управления аккаунтами
Обработка команд добавления, просмотра и управления Telegram-аккаунтами.
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold, hcode

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import (
    get_accounts_menu_keyboard,
    get_account_actions_keyboard,
    get_style_selection_keyboard,
    get_confirmation_keyboard,
    get_main_menu_keyboard
)
from admin_bot.states import AddAccountStates, AuthAccountStates
from shared.database.engine import get_session
from shared.database.crud import (
    create_account,
    get_all_accounts,
    get_account_by_id,
    get_account_by_label,
    get_account_by_tg_id,
    update_account_status,
    delete_account
)
from shared.database.models import CommunicationStyle, Account
from shared.auth.account_auth import AccountAuthorizer
from shared.locales import t
from telethon.errors import SessionPasswordNeededError
from sqlalchemy import update
import asyncio


router = Router(name="accounts_router")

# Константы
ACCOUNTS_PER_PAGE = 10


## Обработка кнопки "Добавить аккаунт"
@router.callback_query(F.data == "accounts:add", OperatorFilter())
async def callback_add_account(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Начало процесса добавления аккаунта через кнопку.
    """
    await state.set_state(AddAccountStates.waiting_for_label)

    await callback.message.answer(
        t("accounts.add_title", lang) + t("accounts.add_label_prompt", lang)
    )

    await callback.answer()


## Команда /add_account
@router.message(Command("add_account"), OperatorFilter())
async def cmd_add_account(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Начало процесса добавления аккаунта через команду.
    """
    await state.set_state(AddAccountStates.waiting_for_label)

    await message.answer(
        t("accounts.add_title", lang) + t("accounts.add_label_prompt_cmd", lang)
    )


## Обработка названия аккаунта
## Обработка названия аккаунта (исключаем команды)
@router.message(AddAccountStates.waiting_for_label, OperatorFilter(), ~F.text.startswith("/"))
async def process_account_label(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает название аккаунта.
    """
    label = message.text.strip()

    if not label or len(label) < 2:
        await message.answer(t("accounts.label_short", lang))
        return

    if len(label) > 100:
        await message.answer(t("accounts.label_long", lang))
        return

    # Проверяем уникальность
    async with get_session() as session:
        existing = await get_account_by_label(session, label)
        if existing:
            await message.answer(
                t("accounts.label_exists", lang, label=hbold(label))
            )
            return

    # Сохраняем label
    await state.update_data(label=label)
    await state.set_state(AddAccountStates.waiting_for_phone)

    await message.answer(
        t("accounts.phone_prompt", lang, label=hbold(label))
    )


## Обработка номера телефона (исключаем команды)
@router.message(AddAccountStates.waiting_for_phone, OperatorFilter(), ~F.text.startswith("/"))
async def process_account_phone(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает номер телефона аккаунта.
    """
    phone = message.text.strip()

    # Базовая валидация номера
    if not phone.startswith("+"):
        await message.answer(t("accounts.phone_no_plus", lang))
        return

    if len(phone) < 11:
        await message.answer(t("accounts.phone_short", lang))
        return

    ## Сохраняем телефон, спрашиваем роль
    await state.update_data(phone=phone)
    await state.set_state(AddAccountStates.waiting_for_role)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=t("accounts.role_monitor", lang), callback_data="add_account:role:monitor")
    builder.button(text=t("accounts.role_reply", lang), callback_data="add_account:role:reply")
    builder.adjust(1)

    await message.answer(
        t("accounts.role_prompt", lang),
        reply_markup=builder.as_markup()
    )


## Callback выбора роли при добавлении
@router.callback_query(
    F.data.startswith("add_account:role:"),
    AddAccountStates.waiting_for_role,
    OperatorFilter()
)
async def process_account_role(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает выбор роли и создаёт аккаунт.
    """
    role = callback.data.split(":")[-1]

    data = await state.get_data()
    label = data.get("label")
    phone = data.get("phone")

    if not label or not phone:
        await callback.answer(t("accounts.data_lost", lang), show_alert=True)
        await state.clear()
        return

    async with get_session() as session:
        try:
            new_account = await create_account(
                session,
                label=label,
                tg_user_id=0,
                phone=phone,
                style_default=CommunicationStyle.FRIENDLY.value,
                enabled=False
            )
            ## Устанавливаем роль
            new_account.role = role
            await session.commit()

            role_name = t(f"accounts.role_names.{role}", lang) if role in ("monitor", "reply", "both") else role

            cli_cmd = hcode('docker exec -it leadhunter_lead_listener python lead_listener/auth_cli.py')

            await state.clear()
            await callback.message.edit_text(
                t("accounts.added_ok", lang,
                  label=hbold(label),
                  phone=hcode(phone),
                  role=role_name,
                  id=new_account.id,
                  cli_cmd=cli_cmd),
                reply_markup=get_accounts_menu_keyboard(lang)
            )
            await callback.answer(t("accounts.added_toast", lang))
        except Exception as e:
            await state.clear()
            await callback.answer(t("accounts.add_error", lang, error=str(e)), show_alert=True)


## Команда /list_accounts
@router.message(Command("list_accounts"), OperatorFilter())
async def cmd_list_accounts(message: Message, lang: str = "ru"):
    """
    Показывает список всех аккаунтов.
    """
    async with get_session() as session:
        accounts = await get_all_accounts(session, enabled_only=False)

    if not accounts:
        await message.answer(
            t("accounts.empty_cmd", lang),
            reply_markup=get_accounts_menu_keyboard(lang)
        )
        return

    # Формируем текст списка
    text_lines = [t("accounts.list_title", lang, count=len(accounts))]

    for account in accounts[:ACCOUNTS_PER_PAGE]:
        status_icon = "🟢" if account.enabled else "🔴"
        role = getattr(account, 'role', 'both')
        role_icon = "📡" if role == "monitor" else "💬" if role == "reply" else "🔄"

        text_lines.append(
            f"{status_icon} {role_icon} {hbold(account.label)}\n"
            f"   ID: #{account.id} | {account.phone or t('accounts.not_found', lang)}"
        )
        text_lines.append("")

    text = "\n".join(text_lines)

    # Создаём клавиатуру
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for account in accounts[:ACCOUNTS_PER_PAGE]:
        status_icon = "🟢" if account.enabled else "🔴"
        builder.button(
            text=f"{status_icon} {account.label}",
            callback_data=f"account:view:{account.id}"
        )

    builder.button(text=t("accounts.btn_add", lang), callback_data="accounts:add")
    builder.button(text=t("menu.back", lang), callback_data="menu:main")

    builder.adjust(1, 1, 2)

    await message.answer(text, reply_markup=builder.as_markup())


## Callback меню аккаунтов
@router.callback_query(F.data == "menu:accounts", OperatorFilter())
async def callback_accounts_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик callback меню аккаунтов.
    """
    await callback.message.edit_text(
        t("accounts.menu_title", lang),
        reply_markup=get_accounts_menu_keyboard(lang)
    )
    await callback.answer()


## Callback список аккаунтов
@router.callback_query(F.data == "accounts:list", OperatorFilter())
async def callback_list_accounts(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает список аккаунтов через callback.
    """
    async with get_session() as session:
        accounts = await get_all_accounts(session, enabled_only=False)

    if not accounts:
        await callback.message.edit_text(
            t("accounts.empty", lang),
            reply_markup=get_accounts_menu_keyboard(lang)
        )
        await callback.answer()
        return

    text_lines = [t("accounts.list_title", lang, count=len(accounts))]

    for account in accounts[:ACCOUNTS_PER_PAGE]:
        status_icon = "🟢" if account.enabled else "🔴"
        role = getattr(account, 'role', 'both')
        role_icon = "📡" if role == "monitor" else "💬" if role == "reply" else "🔄"

        text_lines.append(
            f"{status_icon} {role_icon} {hbold(account.label)}\n"
            f"   ID: #{account.id}"
        )
        text_lines.append("")

    text = "\n".join(text_lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for account in accounts[:ACCOUNTS_PER_PAGE]:
        status_icon = "🟢" if account.enabled else "🔴"
        builder.button(
            text=f"{status_icon} {account.label}",
            callback_data=f"account:view:{account.id}"
        )

    builder.button(text=t("menu.back", lang), callback_data="menu:accounts")
    builder.adjust(1, 1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


## Callback просмотра аккаунта
@router.callback_query(F.data.startswith("account:view:"), OperatorFilter())
async def callback_view_account(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает подробную информацию об аккаунте.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        account = await get_account_by_id(session, account_id)

    if not account:
        await callback.answer(t("accounts.not_found", lang), show_alert=True)
        return

    text = t("accounts.card_title", lang, label=account.label)
    text += t("accounts.card_db_id", lang, id=account.id)

    if account.tg_user_id and account.tg_user_id != 0:
        text += t("accounts.card_tg_id", lang, tg_id=hcode(str(account.tg_user_id)))

    if account.phone:
        text += t("accounts.card_phone", lang, phone=hcode(account.phone))

    if account.username:
        text += t("accounts.card_username", lang, username=account.username)

    account_role = getattr(account, 'role', 'both')
    role_name = t(f"accounts.role_names.{account_role}", lang) if account_role in ("monitor", "reply", "both") else account_role
    text += t("accounts.card_role", lang, role=role_name)
    text += t("accounts.card_status_on", lang) if account.enabled else t("accounts.card_status_off", lang)

    ## Аккаунт считается авторизованным только если tg_user_id положительный (реальный Telegram ID)
    is_authorized = account.tg_user_id is not None and account.tg_user_id > 0

    await callback.message.edit_text(
        text,
        reply_markup=get_account_actions_keyboard(account.id, account.enabled, is_authorized)
    )
    await callback.answer()


## Callback активации аккаунта
@router.callback_query(F.data.startswith("account:enable:"), OperatorFilter())
async def callback_enable_account(callback: CallbackQuery, lang: str = "ru"):
    """
    Активирует аккаунт.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await update_account_status(session, account_id, enabled=True)
        await session.commit()

        if success:
            account = await get_account_by_id(session, account_id)
            await callback.answer(t("accounts.enabled", lang), show_alert=False)

            await callback.message.edit_text(
                t("accounts.enabled_text", lang, label=account.label),
                reply_markup=get_account_actions_keyboard(account.id, True)
            )
        else:
            await callback.answer(t("accounts.enable_error", lang), show_alert=True)


## Callback деактивации аккаунта
@router.callback_query(F.data.startswith("account:disable:"), OperatorFilter())
async def callback_disable_account(callback: CallbackQuery, lang: str = "ru"):
    """
    Деактивирует аккаунт.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await update_account_status(session, account_id, enabled=False)
        await session.commit()

        if success:
            account = await get_account_by_id(session, account_id)
            await callback.answer(t("accounts.disabled", lang), show_alert=False)

            await callback.message.edit_text(
                t("accounts.disabled_text", lang, label=account.label),
                reply_markup=get_account_actions_keyboard(account.id, False)
            )
        else:
            await callback.answer(t("accounts.disable_error", lang), show_alert=True)


## Callback изменения роли
@router.callback_query(F.data.startswith("account:change_role:"), OperatorFilter())
async def callback_change_role(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает меню выбора роли аккаунта.
    """
    account_id = int(callback.data.split(":")[2])

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for role in ("monitor", "reply", "both"):
        builder.button(
            text=t(f"accounts.role_names.{role}", lang),
            callback_data=f"account:set_role:{account_id}:{role}"
        )
    builder.button(text=t("menu.back", lang), callback_data=f"account:view:{account_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        t("accounts.role_prompt", lang),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


## Callback установки роли
@router.callback_query(F.data.startswith("account:set_role:"), OperatorFilter())
async def callback_set_role(callback: CallbackQuery, lang: str = "ru"):
    """
    Сохраняет новую роль аккаунта.
    """
    parts = callback.data.split(":")
    account_id = int(parts[2])
    new_role = parts[3]

    async with get_session() as session:
        result = await session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(role=new_role)
        )
        await session.commit()

        if result.rowcount > 0:
            account = await get_account_by_id(session, account_id)
            role_name = t(f"accounts.role_names.{new_role}", lang)
            await callback.answer(t("accounts.role_changed", lang, role=role_name), show_alert=False)
            is_authorized = account.tg_user_id is not None and account.tg_user_id > 0
            await callback.message.edit_text(
                t("accounts.card_title", lang, label=account.label)
                + t("accounts.card_db_id", lang, id=account.id)
                + t("accounts.card_role", lang, role=role_name)
                + (t("accounts.card_status_on", lang) if account.enabled else t("accounts.card_status_off", lang)),
                reply_markup=get_account_actions_keyboard(account.id, account.enabled, is_authorized, lang)
            )
        else:
            await callback.answer(t("accounts.role_error", lang), show_alert=True)


## Callback изменения стиля (legacy — оставлен для совместимости)
@router.callback_query(F.data.startswith("account:change_style:"), OperatorFilter())
async def callback_change_style(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает меню выбора стиля.
    """
    account_id = int(callback.data.split(":")[2])

    await callback.message.edit_text(
        t("accounts.style_prompt", lang),
        reply_markup=get_style_selection_keyboard(account_id)
    )
    await callback.answer()


## Callback установки стиля
@router.callback_query(F.data.startswith("account:style:"), OperatorFilter())
async def callback_set_style(callback: CallbackQuery, lang: str = "ru"):
    """
    Устанавливает новый стиль для аккаунта.
    """
    parts = callback.data.split(":")
    account_id = int(parts[2])
    new_style = parts[3]

    async with get_session() as session:
        # Обновляем стиль
        result = await session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(style_default=new_style)
        )
        await session.commit()

        if result.rowcount > 0:
            account = await get_account_by_id(session, account_id)

            style_name = t(f"accounts.style_names.{new_style}", lang)

            await callback.answer(
                t("accounts.style_changed", lang, style=style_name),
                show_alert=False
            )

            await callback.message.edit_text(
                t("accounts.style_changed_text", lang, label=account.label),
                reply_markup=get_account_actions_keyboard(account.id, account.enabled)
            )
        else:
            await callback.answer(t("accounts.style_error", lang), show_alert=True)


## Callback удаления аккаунта
@router.callback_query(F.data.startswith("account:delete:"), OperatorFilter())
async def callback_delete_account(callback: CallbackQuery, lang: str = "ru"):
    """
    Запрашивает подтверждение удаления аккаунта.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        account = await get_account_by_id(session, account_id)

    if not account:
        await callback.answer(t("accounts.not_found", lang), show_alert=True)
        return

    await callback.message.edit_text(
        t("accounts.delete_confirm", lang, label=hbold(account.label)),
        reply_markup=get_confirmation_keyboard("delete", account_id, "account")
    )
    await callback.answer()


## Callback подтверждения удаления
@router.callback_query(F.data.startswith("account:delete_confirm:"), OperatorFilter())
async def callback_delete_account_confirm(callback: CallbackQuery, lang: str = "ru"):
    """
    Подтверждает и выполняет удаление аккаунта.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        account = await get_account_by_id(session, account_id)
        account_label = account.label if account else "?"

        success = await delete_account(session, account_id)
        await session.commit()

    if success:
        await callback.message.edit_text(
            t("accounts.deleted", lang, label=hbold(account_label)),
            reply_markup=get_accounts_menu_keyboard(lang)
        )
        await callback.answer(t("accounts.deleted_toast", lang))
    else:
        await callback.answer(t("accounts.delete_error", lang), show_alert=True)


## Callback отмены действия
@router.callback_query(F.data.startswith("account:cancel:"), OperatorFilter())
async def callback_cancel_account_action(callback: CallbackQuery, lang: str = "ru"):
    """
    Отменяет действие и возвращает к карточке аккаунта.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        account = await get_account_by_id(session, account_id)

    if account:
        await callback.message.edit_text(
            t("accounts.action_cancelled_text", lang, label=account.label),
            reply_markup=get_account_actions_keyboard(account.id, account.enabled)
        )

    await callback.answer(t("accounts.action_cancelled", lang))


## Обработка отмены во время добавления аккаунта
@router.message(Command("cancel"), AddAccountStates())
async def cancel_add_account(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет процесс добавления аккаунта.
    """
    await state.clear()
    await message.answer(
        t("accounts.add_cancelled", lang),
        reply_markup=get_accounts_menu_keyboard(lang)
    )


## Callback авторизации аккаунта
@router.callback_query(F.data.startswith("account:auth:"), OperatorFilter())
async def callback_auth_account(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Начинает процесс авторизации аккаунта.
    """
    account_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        account = await get_account_by_id(session, account_id)

    if not account:
        await callback.answer(t("accounts.not_found", lang), show_alert=True)
        return

    if not account.phone:
        await callback.answer(t("accounts.auth_no_phone", lang), show_alert=True)
        return

    ## Проверяем, не авторизован ли уже (только положительные ID - реальные Telegram ID)
    if account.tg_user_id and account.tg_user_id > 0:
        await callback.answer(t("accounts.auth_already", lang), show_alert=True)
        return

    # Сохраняем данные в state
    await state.update_data(account_id=account_id, phone=account.phone)
    await state.set_state(AuthAccountStates.waiting_for_code)

    # Создаём авторизатор и отправляем код
    authorizer = AccountAuthorizer(account_id, account.phone)

    try:
        # Создаём временный клиент для отправки кода
        from telethon import TelegramClient
        from config import settings

        session_file = settings.sessions_dir / f"temp_auth_{account_id}.session"
        client = TelegramClient(
            str(session_file),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        await client.connect()
        await client.send_code_request(account.phone)
        await client.disconnect()

        await callback.message.edit_text(
            t("accounts.auth_title", lang, label=account.label)
            + t("accounts.auth_phone", lang, phone=hcode(account.phone))
            + t("accounts.auth_code_sent", lang)
        )
        await callback.answer()

    except Exception as e:
        await callback.answer(t("accounts.add_error", lang, error=str(e)), show_alert=True)
        await state.clear()


## Обработка кода авторизации (исключаем команды)
@router.message(AuthAccountStates.waiting_for_code, OperatorFilter(), ~F.text.startswith("/"))
async def process_auth_code(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает код авторизации.
    """
    code = message.text.strip()

    if not code.isdigit() or len(code) != 5:
        await message.answer(t("accounts.auth_code_invalid", lang))
        return

    data = await state.get_data()
    account_id = data.get("account_id")
    phone = data.get("phone")

    if not account_id or not phone:
        await message.answer(t("accounts.auth_data_lost", lang))
        await state.clear()
        return

    # Сохраняем код в state
    await state.update_data(auth_code=code)

    # Создаём авторизатор
    async def get_code():
        return code

    authorizer = AccountAuthorizer(account_id, phone, get_code, None)

    # Запускаем авторизацию (без пароля)
    success, error, tg_user_id, username = await authorizer.authorize()

    if success:
        await state.clear()
        await message.answer(
            t("accounts.auth_success", lang,
              tg_id=hcode(str(tg_user_id)),
              username=username or t("accounts.not_found", lang)),
            reply_markup=get_accounts_menu_keyboard(lang)
        )
    elif error == "NEEDS_PASSWORD":
        # Нужен 2FA пароль
        await state.set_state(AuthAccountStates.waiting_for_password)
        # Сохраняем путь к сессии для повторного использования
        from config import settings
        session_path = settings.sessions_dir / f"temp_auth_{account_id}.session"
        await state.update_data(session_path=str(session_path))
        await message.answer(t("accounts.auth_2fa_prompt", lang))
    else:
        await state.clear()
        await message.answer(
            t("accounts.auth_error", lang, error=error),
            reply_markup=get_accounts_menu_keyboard(lang)
        )


## Обработка 2FA пароля (исключаем команды)
@router.message(AuthAccountStates.waiting_for_password, OperatorFilter(), ~F.text.startswith("/"))
async def process_auth_password(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает 2FA пароль.
    """
    password = message.text.strip()

    if not password:
        await message.answer(t("accounts.auth_password_empty", lang))
        return

    data = await state.get_data()
    account_id = data.get("account_id")
    phone = data.get("phone")
    auth_code = data.get("auth_code")
    session_path = data.get("session_path")

    if not account_id or not phone or not auth_code:
        await message.answer(t("accounts.auth_data_lost", lang))
        await state.clear()
        return

    # Создаём авторизатор заново с тем же кодом
    async def get_code():
        return auth_code

    authorizer = AccountAuthorizer(account_id, phone, get_code, None)

    # Если есть сохранённая сессия, используем её
    if session_path:
        from pathlib import Path
        from telethon import TelegramClient
        from config import settings

        # Подключаемся к существующему клиенту
        client = TelegramClient(
            session_path,
            settings.telegram_api_id,
            settings.telegram_api_hash
        )
        await client.connect()
        authorizer.client = client

    # Запускаем авторизацию с паролем
    success, error, tg_user_id, username = await authorizer.authorize(password=password)

    await state.clear()

    if success:
        await message.answer(
            t("accounts.auth_success", lang,
              tg_id=hcode(str(tg_user_id)),
              username=username or t("accounts.not_found", lang)),
            reply_markup=get_accounts_menu_keyboard(lang)
        )
    else:
        await message.answer(
            t("accounts.auth_error_2fa", lang, error=error),
            reply_markup=get_accounts_menu_keyboard(lang)
        )


## Обработка отмены авторизации
@router.message(Command("cancel"), AuthAccountStates())
async def cancel_auth_account(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет процесс авторизации аккаунта.
    """
    await state.clear()
    await message.answer(
        t("accounts.auth_cancelled", lang),
        reply_markup=get_accounts_menu_keyboard(lang)
    )
