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
from telethon.errors import SessionPasswordNeededError
from sqlalchemy import update
import asyncio


router = Router(name="accounts_router")

# Константы
ACCOUNTS_PER_PAGE = 10


## Обработка кнопки "Добавить аккаунт"
@router.callback_query(F.data == "accounts:add", OperatorFilter())
async def callback_add_account(callback: CallbackQuery, state: FSMContext):
    """
    Начало процесса добавления аккаунта через кнопку.
    """
    await state.set_state(AddAccountStates.waiting_for_label)
    
    await callback.message.answer(
        "➕ <b>Добавление Telegram-аккаунта</b>\n\n"
        "Аккаунты используются для отправки ответов на лиды.\n\n"
        "📝 Введите название (label) для этого аккаунта.\n"
        "(Например: Рабочий 1, Основной)\n\n"
        "Отправьте /cancel для отмены."
    )
    
    await callback.answer()


## Команда /add_account
@router.message(Command("add_account"), OperatorFilter())
async def cmd_add_account(message: Message, state: FSMContext):
    """
    Начало процесса добавления аккаунта через команду.
    """
    await state.set_state(AddAccountStates.waiting_for_label)
    
    await message.answer(
        "➕ <b>Добавление Telegram-аккаунта</b>\n\n"
        "Аккаунты используются для отправки ответов на лиды.\n\n"
        "📝 Введите название (label) для этого аккаунта.\n"
        "Например: «Основной», «Резервный», «Account1»\n\n"
        "💡 Название должно быть уникальным.\n\n"
        "Отправьте /cancel для отмены."
    )


## Обработка названия аккаунта
## Обработка названия аккаунта (исключаем команды)
@router.message(AddAccountStates.waiting_for_label, OperatorFilter(), ~F.text.startswith("/"))
async def process_account_label(message: Message, state: FSMContext):
    """
    Обрабатывает название аккаунта.
    """
    label = message.text.strip()
    
    if not label or len(label) < 2:
        await message.answer(
            "❌ Название слишком короткое.\n"
            "Введите название минимум из 2 символов."
        )
        return
    
    if len(label) > 100:
        await message.answer(
            "❌ Название слишком длинное (макс 100 символов).\n"
            "Введите более короткое название."
        )
        return
    
    # Проверяем уникальность
    async with get_session() as session:
        existing = await get_account_by_label(session, label)
        if existing:
            await message.answer(
                f"❌ Аккаунт с названием {hbold(label)} уже существует.\n"
                "Введите другое название."
            )
            return
    
    # Сохраняем label
    await state.update_data(label=label)
    await state.set_state(AddAccountStates.waiting_for_phone)
    
    await message.answer(
        f"✅ Название: {hbold(label)}\n\n"
        "📱 Теперь введите номер телефона аккаунта.\n"
        "Формат: +7XXXXXXXXXX или +380XXXXXXXXX\n\n"
        "Отправьте /cancel для отмены."
    )


## Обработка номера телефона (исключаем команды)
@router.message(AddAccountStates.waiting_for_phone, OperatorFilter(), ~F.text.startswith("/"))
async def process_account_phone(message: Message, state: FSMContext):
    """
    Обрабатывает номер телефона аккаунта.
    """
    phone = message.text.strip()
    
    # Базовая валидация номера
    if not phone.startswith("+"):
        await message.answer(
            "❌ Номер должен начинаться с +\n"
            "Например: +79991234567"
        )
        return
    
    if len(phone) < 11:
        await message.answer(
            "❌ Номер телефона слишком короткий.\n"
            "Введите корректный номер."
        )
        return
    
    ## Сохраняем телефон, спрашиваем роль
    await state.update_data(phone=phone)
    await state.set_state(AddAccountStates.waiting_for_role)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="👁 Мониторинг чатов", callback_data="add_account:role:monitor")
    builder.button(text="✉️ Ответы + поиск", callback_data="add_account:role:reply")
    builder.adjust(1)

    await message.answer(
        "🎭 <b>Выберите роль аккаунта:</b>\n\n"
        "👁 <b>Мониторинг</b> — подписан на чаты, слушает сообщения\n"
        "✉️ <b>Ответы + поиск</b> — отправка ответов на лиды, Premium-поиск",
        reply_markup=builder.as_markup()
    )


## Callback выбора роли при добавлении
@router.callback_query(
    F.data.startswith("add_account:role:"),
    AddAccountStates.waiting_for_role,
    OperatorFilter()
)
async def process_account_role(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор роли и создаёт аккаунт.
    """
    role = callback.data.split(":")[-1]

    data = await state.get_data()
    label = data.get("label")
    phone = data.get("phone")

    if not label or not phone:
        await callback.answer("❌ Данные потеряны", show_alert=True)
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

            role_names = {"monitor": "👁 Мониторинг", "reply": "✉️ Ответы + поиск"}

            await state.clear()
            await callback.message.edit_text(
                f"✅ <b>Аккаунт добавлен!</b>\n\n"
                f"📝 <b>Название:</b> {hbold(label)}\n"
                f"📱 <b>Телефон:</b> {hcode(phone)}\n"
                f"🎭 <b>Роль:</b> {role_names.get(role, role)}\n"
                f"🆔 <b>ID:</b> #{new_account.id}\n\n"
                f"⚠️ Авторизуйте аккаунт через CLI на сервере:\n"
                f"{hcode('docker exec -it leadhunter_lead_listener python lead_listener/auth_cli.py')}",
                reply_markup=get_accounts_menu_keyboard()
            )
            await callback.answer("✅ Аккаунт добавлен")
        except Exception as e:
            await state.clear()
            await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


## Команда /list_accounts
@router.message(Command("list_accounts"), OperatorFilter())
async def cmd_list_accounts(message: Message):
    """
    Показывает список всех аккаунтов.
    """
    async with get_session() as session:
        accounts = await get_all_accounts(session, enabled_only=False)
    
    if not accounts:
        await message.answer(
            "📭 <b>Список аккаунтов пуст</b>\n\n"
            "Добавьте аккаунты командой /add_account",
            reply_markup=get_accounts_menu_keyboard()
        )
        return
    
    # Формируем текст списка
    text_lines = [f"👤 <b>Список аккаунтов ({len(accounts)})</b>\n"]
    
    style_emoji = {
        CommunicationStyle.POLITE.value: "🎩",
        CommunicationStyle.FRIENDLY.value: "😊",
        CommunicationStyle.AGGRESSIVE.value: "💪"
    }
    
    for account in accounts[:ACCOUNTS_PER_PAGE]:
        status_icon = "🟢" if account.enabled else "🔴"
        style_icon = style_emoji.get(account.style_default, "📝")
        
        text_lines.append(
            f"{status_icon} {style_icon} {hbold(account.label)}\n"
            f"   ID: #{account.id} | {account.phone or 'Нет телефона'}"
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
    
    builder.button(text="➕ Добавить аккаунт", callback_data="accounts:add")
    builder.button(text="🔙 Назад", callback_data="menu:main")
    
    builder.adjust(1, 1, 2)
    
    await message.answer(text, reply_markup=builder.as_markup())


## Callback меню аккаунтов
@router.callback_query(F.data == "menu:accounts", OperatorFilter())
async def callback_accounts_menu(callback: CallbackQuery):
    """
    Обработчик callback меню аккаунтов.
    """
    await callback.message.edit_text(
        "👤 <b>Управление аккаунтами</b>\n\n"
        "Здесь вы можете добавлять Telegram-аккаунты, "
        "которые будут использоваться для отправки ответов на лиды.",
        reply_markup=get_accounts_menu_keyboard()
    )
    await callback.answer()


## Callback список аккаунтов
@router.callback_query(F.data == "accounts:list", OperatorFilter())
async def callback_list_accounts(callback: CallbackQuery):
    """
    Показывает список аккаунтов через callback.
    """
    async with get_session() as session:
        accounts = await get_all_accounts(session, enabled_only=False)
    
    if not accounts:
        await callback.message.edit_text(
            "📭 <b>Список аккаунтов пуст</b>\n\n"
            "Добавьте аккаунты для отправки сообщений.",
            reply_markup=get_accounts_menu_keyboard()
        )
        await callback.answer()
        return
    
    text_lines = [f"👤 <b>Список аккаунтов ({len(accounts)})</b>\n"]
    
    style_emoji = {
        CommunicationStyle.POLITE.value: "🎩",
        CommunicationStyle.FRIENDLY.value: "😊",
        CommunicationStyle.AGGRESSIVE.value: "💪"
    }
    
    for account in accounts[:ACCOUNTS_PER_PAGE]:
        status_icon = "🟢" if account.enabled else "🔴"
        style_icon = style_emoji.get(account.style_default, "📝")
        
        text_lines.append(
            f"{status_icon} {style_icon} {hbold(account.label)}\n"
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
    
    builder.button(text="🔙 Назад", callback_data="menu:accounts")
    builder.adjust(1, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


## Callback просмотра аккаунта
@router.callback_query(F.data.startswith("account:view:"), OperatorFilter())
async def callback_view_account(callback: CallbackQuery):
    """
    Показывает подробную информацию об аккаунте.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        account = await get_account_by_id(session, account_id)
    
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    
    role_names = {
        "monitor": "👁 Мониторинг",
        "reply": "✉️ Ответы + поиск",
        "both": "🔄 Мониторинг + ответы"
    }

    text = (
        f"👤 <b>{account.label}</b>\n\n"
        f"🆔 <b>ID в БД:</b> #{account.id}\n"
    )

    if account.tg_user_id and account.tg_user_id != 0:
        text += f"🆔 <b>Telegram ID:</b> {hcode(str(account.tg_user_id))}\n"

    if account.phone:
        text += f"📱 <b>Телефон:</b> {hcode(account.phone)}\n"

    if account.username:
        text += f"🔗 <b>Username:</b> @{account.username}\n"

    account_role = getattr(account, 'role', 'both')
    text += (
        f"🎭 <b>Роль:</b> {role_names.get(account_role, account_role)}\n"
        f"✅ <b>Статус:</b> {'Активен 🟢' if account.enabled else 'Неактивен 🔴'}\n"
    )
    
    ## Аккаунт считается авторизованным только если tg_user_id положительный (реальный Telegram ID)
    is_authorized = account.tg_user_id is not None and account.tg_user_id > 0
    
    await callback.message.edit_text(
        text,
        reply_markup=get_account_actions_keyboard(account.id, account.enabled, is_authorized)
    )
    await callback.answer()


## Callback активации аккаунта
@router.callback_query(F.data.startswith("account:enable:"), OperatorFilter())
async def callback_enable_account(callback: CallbackQuery):
    """
    Активирует аккаунт.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        success = await update_account_status(session, account_id, enabled=True)
        await session.commit()
        
        if success:
            account = await get_account_by_id(session, account_id)
            await callback.answer("✅ Аккаунт активирован", show_alert=False)
            
            text = (
                f"👤 <b>{account.label}</b>\n\n"
                f"✅ Аккаунт активирован и готов к работе."
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_account_actions_keyboard(account.id, True)
            )
        else:
            await callback.answer("❌ Ошибка при активации", show_alert=True)


## Callback деактивации аккаунта
@router.callback_query(F.data.startswith("account:disable:"), OperatorFilter())
async def callback_disable_account(callback: CallbackQuery):
    """
    Деактивирует аккаунт.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        success = await update_account_status(session, account_id, enabled=False)
        await session.commit()
        
        if success:
            account = await get_account_by_id(session, account_id)
            await callback.answer("🔴 Аккаунт деактивирован", show_alert=False)
            
            text = (
                f"👤 <b>{account.label}</b>\n\n"
                f"🔴 Аккаунт деактивирован."
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_account_actions_keyboard(account.id, False)
            )
        else:
            await callback.answer("❌ Ошибка при деактивации", show_alert=True)


## Callback изменения стиля
@router.callback_query(F.data.startswith("account:change_style:"), OperatorFilter())
async def callback_change_style(callback: CallbackQuery):
    """
    Показывает меню выбора стиля.
    """
    account_id = int(callback.data.split(":")[2])
    
    await callback.message.edit_text(
        "🎨 <b>Выберите новый стиль общения:</b>\n\n"
        "🎩 <b>Вежливый/Деловой</b> — официальный тон\n"
        "😊 <b>Дружеский</b> — неформальное общение\n"
        "💪 <b>Агрессивный</b> — напористый стиль",
        reply_markup=get_style_selection_keyboard(account_id)
    )
    await callback.answer()


## Callback установки стиля
@router.callback_query(F.data.startswith("account:style:"), OperatorFilter())
async def callback_set_style(callback: CallbackQuery):
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
            
            style_names = {
                CommunicationStyle.POLITE.value: "Вежливый/Деловой",
                CommunicationStyle.FRIENDLY.value: "Дружеский",
                CommunicationStyle.AGGRESSIVE.value: "Агрессивный"
            }
            
            await callback.answer(
                f"✅ Стиль изменён на {style_names.get(new_style, new_style)}",
                show_alert=False
            )
            
            text = (
                f"👤 <b>{account.label}</b>\n\n"
                f"🎨 Стиль успешно изменён."
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_account_actions_keyboard(account.id, account.enabled)
            )
        else:
            await callback.answer("❌ Ошибка при изменении стиля", show_alert=True)


## Callback удаления аккаунта
@router.callback_query(F.data.startswith("account:delete:"), OperatorFilter())
async def callback_delete_account(callback: CallbackQuery):
    """
    Запрашивает подтверждение удаления аккаунта.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        account = await get_account_by_id(session, account_id)
    
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"⚠️ <b>Подтвердите удаление</b>\n\n"
        f"Вы действительно хотите удалить аккаунт {hbold(account.label)}?\n\n"
        f"❗ Все связанные отправленные сообщения останутся в истории.",
        reply_markup=get_confirmation_keyboard("delete", account_id, "account")
    )
    await callback.answer()


## Callback подтверждения удаления
@router.callback_query(F.data.startswith("account:delete_confirm:"), OperatorFilter())
async def callback_delete_account_confirm(callback: CallbackQuery):
    """
    Подтверждает и выполняет удаление аккаунта.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        account = await get_account_by_id(session, account_id)
        account_label = account.label if account else "Неизвестный аккаунт"
        
        success = await delete_account(session, account_id)
        await session.commit()
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Аккаунт удалён</b>\n\n"
            f"Аккаунт {hbold(account_label)} успешно удалён.",
            reply_markup=get_accounts_menu_keyboard()
        )
        await callback.answer("🗑 Аккаунт удалён")
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


## Callback отмены действия
@router.callback_query(F.data.startswith("account:cancel:"), OperatorFilter())
async def callback_cancel_account_action(callback: CallbackQuery):
    """
    Отменяет действие и возвращает к карточке аккаунта.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        account = await get_account_by_id(session, account_id)
    
    if account:
        text = (
            f"👤 <b>{account.label}</b>\n\n"
            f"Действие отменено."
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_account_actions_keyboard(account.id, account.enabled)
        )
    
    await callback.answer("Действие отменено")


## Обработка отмены во время добавления аккаунта
@router.message(Command("cancel"), AddAccountStates())
async def cancel_add_account(message: Message, state: FSMContext):
    """
    Отменяет процесс добавления аккаунта.
    """
    await state.clear()
    await message.answer(
        "❌ Добавление аккаунта отменено.",
        reply_markup=get_accounts_menu_keyboard()
    )


## Callback авторизации аккаунта
@router.callback_query(F.data.startswith("account:auth:"), OperatorFilter())
async def callback_auth_account(callback: CallbackQuery, state: FSMContext):
    """
    Начинает процесс авторизации аккаунта.
    """
    account_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        account = await get_account_by_id(session, account_id)
    
    if not account:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    
    if not account.phone:
        await callback.answer("❌ У аккаунта нет номера телефона", show_alert=True)
        return
    
    ## Проверяем, не авторизован ли уже (только положительные ID - реальные Telegram ID)
    if account.tg_user_id and account.tg_user_id > 0:
        await callback.answer("✅ Аккаунт уже авторизован", show_alert=True)
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
            f"🔐 <b>Авторизация аккаунта {account.label}</b>\n\n"
            f"📱 <b>Телефон:</b> {hcode(account.phone)}\n\n"
            f"✅ Код авторизации отправлен в Telegram!\n\n"
            f"📝 Введите код из Telegram (5 цифр):\n\n"
            f"Отправьте /cancel для отмены."
        )
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        await state.clear()


## Обработка кода авторизации (исключаем команды)
@router.message(AuthAccountStates.waiting_for_code, OperatorFilter(), ~F.text.startswith("/"))
async def process_auth_code(message: Message, state: FSMContext):
    """
    Обрабатывает код авторизации.
    """
    code = message.text.strip()
    
    if not code.isdigit() or len(code) != 5:
        await message.answer(
            "❌ Код должен состоять из 5 цифр.\n"
            "Введите код ещё раз или отправьте /cancel для отмены."
        )
        return
    
    data = await state.get_data()
    account_id = data.get("account_id")
    phone = data.get("phone")
    
    if not account_id or not phone:
        await message.answer("❌ Ошибка: данные потеряны. Начните заново.")
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
            f"✅ <b>Аккаунт успешно авторизован!</b>\n\n"
            f"🆔 <b>Telegram ID:</b> {hcode(str(tg_user_id))}\n"
            f"🔗 <b>Username:</b> @{username or 'не установлен'}\n\n"
            f"Теперь аккаунт готов к использованию!",
            reply_markup=get_accounts_menu_keyboard()
        )
    elif error == "NEEDS_PASSWORD":
        # Нужен 2FA пароль
        await state.set_state(AuthAccountStates.waiting_for_password)
        # Сохраняем путь к сессии для повторного использования
        from config import settings
        session_path = settings.sessions_dir / f"temp_auth_{account_id}.session"
        await state.update_data(session_path=str(session_path))
        await message.answer(
            "🔒 <b>Требуется пароль двухфакторной аутентификации</b>\n\n"
            "Введите пароль 2FA:\n\n"
            "Отправьте /cancel для отмены."
        )
    else:
        await state.clear()
        await message.answer(
            f"❌ <b>Ошибка авторизации</b>\n\n"
            f"{error}\n\n"
            f"Попробуйте ещё раз или отправьте /cancel.",
            reply_markup=get_accounts_menu_keyboard()
        )


## Обработка 2FA пароля (исключаем команды)
@router.message(AuthAccountStates.waiting_for_password, OperatorFilter(), ~F.text.startswith("/"))
async def process_auth_password(message: Message, state: FSMContext):
    """
    Обрабатывает 2FA пароль.
    """
    password = message.text.strip()
    
    if not password:
        await message.answer(
            "❌ Пароль не может быть пустым.\n"
            "Введите пароль ещё раз или отправьте /cancel для отмены."
        )
        return
    
    data = await state.get_data()
    account_id = data.get("account_id")
    phone = data.get("phone")
    auth_code = data.get("auth_code")
    session_path = data.get("session_path")
    
    if not account_id or not phone or not auth_code:
        await message.answer("❌ Ошибка: данные потеряны. Начните заново.")
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
            f"✅ <b>Аккаунт успешно авторизован!</b>\n\n"
            f"🆔 <b>Telegram ID:</b> {hcode(str(tg_user_id))}\n"
            f"🔗 <b>Username:</b> @{username or 'не установлен'}\n\n"
            f"Теперь аккаунт готов к использованию!",
            reply_markup=get_accounts_menu_keyboard()
        )
    else:
        await message.answer(
            f"❌ <b>Ошибка авторизации</b>\n\n"
            f"{error}\n\n"
            f"Попробуйте ещё раз.",
            reply_markup=get_accounts_menu_keyboard()
        )


## Обработка отмены авторизации
@router.message(Command("cancel"), AuthAccountStates())
async def cancel_auth_account(message: Message, state: FSMContext):
    """
    Отменяет процесс авторизации аккаунта.
    """
    await state.clear()
    await message.answer(
        "❌ Авторизация аккаунта отменена.",
        reply_markup=get_accounts_menu_keyboard()
    )

