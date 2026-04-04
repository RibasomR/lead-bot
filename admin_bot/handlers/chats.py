"""
## Хендлеры управления чатами
Обработка команд добавления, просмотра и управления чатами для мониторинга.
"""

from typing import Optional
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold, hcode

from admin_bot.filters import OperatorFilter
from admin_bot.keyboards import (
    get_chats_menu_keyboard,
    get_chat_actions_keyboard,
    get_confirmation_keyboard,
    get_pagination_keyboard,
    get_main_menu_keyboard
)
from admin_bot.states import AddChatStates
from shared.database.engine import get_session
from shared.database.crud import (
    create_chat,
    get_all_chats,
    get_chat_by_id,
    get_chat_by_tg_id,
    update_chat_status,
    update_chat_whitelist,
    update_chat_blacklist,
    delete_chat
)
from shared.database.models import ChatType


router = Router(name="chats_router")

# Константы
CHATS_PER_PAGE = 10


## Обработка кнопки "Добавить чат"
@router.callback_query(F.data == "chats:add", OperatorFilter())
async def callback_add_chat(callback: CallbackQuery, state: FSMContext):
    """
    Начало процесса добавления чата через кнопку.
    """
    await state.set_state(AddChatStates.waiting_for_chat_forward)
    
    await callback.message.answer(
        "➕ <b>Добавление чата в мониторинг</b>\n\n"
        "Выберите способ добавления чата:\n\n"
        "🔗 <b>Способ 1: По ID или username</b>\n"
        "Отправьте Chat ID (например: <code>-1001234567890</code>)\n"
        "или username (например: <code>@pythonru</code>)\n\n"
        "📤 <b>Способ 2: Пересылка сообщения</b>\n"
        "Перешлите любое сообщение из публичного канала\n"
        "(⚠️ для приватных групп работает только способ 1)\n\n"
        "💡 <b>Как узнать Chat ID:</b>\n"
        "1. Добавьте бота @getmyid_bot в группу\n"
        "2. Напишите команду /id\n"
        "3. Скопируйте Chat ID\n\n"
        "Отправьте /cancel для отмены."
    )
    
    await callback.answer()


## Команда /add_chat
@router.message(Command("add_chat"), OperatorFilter())
async def cmd_add_chat(message: Message, state: FSMContext):
    """
    Начало процесса добавления чата через команду.
    """
    await state.set_state(AddChatStates.waiting_for_chat_forward)
    
    await message.answer(
        "➕ <b>Добавление чата в мониторинг</b>\n\n"
        "Выберите способ добавления чата:\n\n"
        "🔗 <b>Способ 1: По ссылке</b>\n"
        "Вставьте ссылку на канал:\n"
        "• <code>https://t.me/pythonru</code>\n"
        "• <code>t.me/pythonru</code>\n\n"
        "📝 <b>Способ 2: По username</b>\n"
        "Отправьте username канала/группы:\n"
        "• С @: <code>@pythonru</code>\n"
        "• Или без @: <code>pythonru</code>\n\n"
        "🆔 <b>Способ 3: По Chat ID</b>\n"
        "Отправьте Chat ID (например: <code>-1001234567890</code>)\n\n"
        "📤 <b>Способ 4: Пересылка сообщения</b>\n"
        "Перешлите любое сообщение из публичного канала\n"
        "(⚠️ для приватных групп работает только способ 2 или 3)\n\n"
        "💡 <b>Как узнать Chat ID:</b>\n"
        "1. Добавьте бота @getmyid_bot в группу\n"
        "2. Напишите команду /id\n"
        "3. Скопируйте Chat ID\n\n"
        "Отправьте /cancel для отмены."
    )


## Обработка пересланного сообщения ОТ ПОЛЬЗОВАТЕЛЯ (не подходит)
@router.message(AddChatStates.waiting_for_chat_forward, OperatorFilter(), F.forward_from)
async def process_user_forward_error(message: Message, state: FSMContext):
    """
    Обрабатывает ошибку когда пользователь переслал сообщение от другого пользователя.
    """
    await message.answer(
        "❌ <b>Неверный тип сообщения</b>\n\n"
        "Вы переслали сообщение от пользователя, а не из группы или канала.\n\n"
        "💡 <b>Как правильно:</b>\n"
        "• Откройте группу или канал, который хотите добавить\n"
        "• Перешлите любое сообщение из этого чата\n"
        "• Не пересылайте личные сообщения от пользователей\n\n"
        "Попробуйте ещё раз или отправьте /cancel для отмены."
    )


## Обработка пересланного сообщения для добавления чата
@router.message(AddChatStates.waiting_for_chat_forward, OperatorFilter(), F.forward_from_chat)
async def process_chat_forward(message: Message, state: FSMContext):
    """
    Обрабатывает пересланное сообщение и извлекает информацию о чате.
    """
    chat = message.forward_from_chat
    
    if not chat:
        await message.answer(
            "❌ Не удалось определить чат из пересланного сообщения.\n"
            "Попробуйте ещё раз или отправьте /cancel."
        )
        return
    
    # Проверяем, не добавлен ли уже этот чат
    async with get_session() as session:
        existing_chat = await get_chat_by_tg_id(session, chat.id)
        
        if existing_chat:
            await message.answer(
                f"⚠️ Чат {hbold(chat.title)} уже добавлен в систему.\n"
                f"ID: #{existing_chat.id}\n\n"
                "Используйте /list_chats для просмотра."
            )
            await state.clear()
            return
        
        # Определяем тип чата
        chat_type = ChatType.GROUP.value
        if chat.type == "channel":
            chat_type = ChatType.CHANNEL.value
        elif chat.type == "supergroup":
            chat_type = ChatType.SUPERGROUP.value
        
        # Создаём чат в БД
        new_chat = await create_chat(
            session,
            tg_chat_id=chat.id,
            title=chat.title or "Без названия",
            chat_type=chat_type,
            username=chat.username,
            priority=1,
            enabled=True
        )
        await session.commit()
    
    await message.answer(
        f"✅ <b>Чат успешно добавлен!</b>\n\n"
        f"📝 <b>Название:</b> {new_chat.title}\n"
        f"🆔 <b>ID чата:</b> {hcode(str(new_chat.tg_chat_id))}\n"
        f"📂 <b>Тип:</b> {new_chat.type}\n"
        f"🔢 <b>Приоритет:</b> {new_chat.priority}\n"
        f"✅ <b>Мониторинг:</b> Включён\n\n"
        "Чат будет отслеживаться на наличие лидов.",
        reply_markup=get_chats_menu_keyboard()
    )
    
    await state.clear()


## Команда /list_chats (с пагинацией)
@router.message(Command("list_chats"), OperatorFilter())
async def cmd_list_chats(message: Message):
    """
    Показывает список всех добавленных чатов (первая страница).
    """
    async with get_session() as session:
        chats = await get_all_chats(session, enabled_only=False, exclude_blacklisted=False)
    
    if not chats:
        await message.answer(
            "📭 <b>Список чатов пуст</b>\n\n"
            "Добавьте чаты для мониторинга командой /add_chat",
            reply_markup=get_chats_menu_keyboard()
        )
        return
    
    # Пагинация
    total_chats = len(chats)
    total_pages = (total_chats + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE
    page = 1
    page_chats = chats[:CHATS_PER_PAGE]
    
    # Формируем текст списка
    text_lines = [
        f"💬 <b>Список чатов</b>\n",
        f"📄 Страница {page}/{total_pages} | Всего: {total_chats}\n"
    ]
    
    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        whitelist_icon = "⚪" if chat.is_whitelisted else ""
        blacklist_icon = "⚫" if chat.is_blacklisted else ""
        
        text_lines.append(
            f"{status_icon} {whitelist_icon}{blacklist_icon} "
            f"{hbold(chat.title)}\n"
            f"   ID: #{chat.id} | Тип: {chat.type}"
        )
        text_lines.append("")
    
    text = "\n".join(text_lines)
    
    # Создаём клавиатуру с кнопками чатов
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        builder.button(
            text=f"{status_icon} {chat.title[:25]}",
            callback_data=f"chat:view:{chat.id}"
        )
    
    # Кнопки навигации (если есть ещё страницы)
    if total_pages > 1:
        builder.button(text="Вперёд ▶️", callback_data="chats:page:2")
    
    builder.button(text="➕ Добавить чат", callback_data="chats:add")
    builder.button(text="🔙 Назад", callback_data="menu:main")
    
    # Adjust: по 1 кнопке чата, навигация, 2 кнопки внизу
    adjust_pattern = [1] * len(page_chats)
    if total_pages > 1:
        adjust_pattern.append(1)  # Навигация
    adjust_pattern.append(2)  # Две кнопки внизу
    builder.adjust(*adjust_pattern)
    
    await message.answer(text, reply_markup=builder.as_markup())


## Callback меню чатов
@router.callback_query(F.data == "menu:chats", OperatorFilter())
async def callback_chats_menu(callback: CallbackQuery):
    """
    Обработчик callback меню чатов.
    """
    ## Считаем статистику чатов
    async with get_session() as session:
        all_chats = await get_all_chats(session)
        enabled_count = sum(1 for c in all_chats if c.enabled)
        total_count = len(all_chats)

    await callback.message.edit_text(
        "💬 <b>Управление чатами</b>\n\n"
        f"📊 Всего: <b>{total_count}</b> | Активных: <b>{enabled_count}</b>\n\n"
        "📋 <b>Мои чаты</b> — список и настройки\n"
        "➕ <b>Добавить</b> — по ссылке, @username или ID\n"
        "🚫 <b>Чёрный список</b> — игнорируемые чаты\n"
        "🔎 <b>Автопоиск</b> — AI-поиск новых каналов\n"
        "📡 <b>Подписать монитор</b> — вступить во все чаты (только monitor-аккаунт)",
        reply_markup=get_chats_menu_keyboard()
    )
    await callback.answer()


## Обработка кнопки "Чёрный список"
@router.callback_query(F.data == "chats:blacklist", OperatorFilter())
async def callback_chats_blacklist(callback: CallbackQuery):
    """Показывает чаты из чёрного списка."""
    async with get_session() as session:
        chats = await get_all_chats(session, enabled_only=False, exclude_blacklisted=False)
        blacklisted = [c for c in chats if c.is_blacklisted]
        
        text = "⚫ <b>Чёрный список чатов</b>\n\n"
        if not blacklisted:
            text += "Список пуст.\n\nДобавляйте чаты для игнорирования."
        else:
            text += f"Найдено: {len(blacklisted)}\n\n"
            for chat in blacklisted[:10]:
                text += f"<b>{chat.title}</b> (<code>{chat.tg_chat_id}</code>)\n"
            if len(blacklisted) > 10:
                text += f"\n<i>...ещё {len(blacklisted) - 10}</i>"
        
        await callback.message.edit_text(text, reply_markup=get_chats_menu_keyboard())
    await callback.answer()


## Автоподписка на все чаты
@router.callback_query(F.data == "chats:join_all", OperatorFilter())
async def callback_join_all_chats(callback: CallbackQuery, state: FSMContext):
    """
    ## Подписка monitor-аккаунта на все активные чаты
    Reply-аккаунты не вступают в чаты — только мониторинг.
    """
    import httpx
    from config import settings

    await callback.answer("🔄 Запускаю подписку монитора...", show_alert=False)

    # Показываем сообщение о процессе
    await callback.message.edit_text(
        "⏳ <b>Подписка монитор-аккаунта</b>\n\n"
        "Подписываю monitor-аккаунт на активные каналы...\n"
        "Это может занять некоторое время.",
        reply_markup=None
    )
    
    try:
        # Формируем URL Lead Listener API (старый способ, но с портом из env)
        port = str(settings.lead_listener_api_port)
        lead_listener_url = settings.admin_bot_api_url.replace('admin_bot', 'lead_listener').replace('8000', port)
        api_url = f"{lead_listener_url}/api/join_all_chats"
        
        async with httpx.AsyncClient(timeout=180.0) as client:  # Увеличенный timeout
            response = await client.post(api_url)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', {})
                details = data.get('details', {})
                
                # Формируем сообщение с результатами
                text = "✅ <b>Автоподписка завершена!</b>\n\n"
                text += f"📊 <b>Статистика:</b>\n"
                text += f"✅ Успешно подписано: {results.get('success', 0)}\n"
                text += f"⏭️ Уже подписаны: {results.get('already_joined', 0)}\n"
                
                if results.get('private', 0) > 0:
                    text += f"🔒 Приватных каналов: {results.get('private', 0)}\n"
                
                if results.get('flood_wait', 0) > 0:
                    text += f"⏳ FloodWait: {results.get('flood_wait', 0)}\n"
                
                if results.get('pending_approval', 0) > 0:
                    text += f"⏳ Ожидают одобрения: {results.get('pending_approval', 0)}\n"
                
                if results.get('errors', 0) > 0:
                    text += f"❌ Ошибок: {results.get('errors', 0)}\n"
                
                # Детали по приватным каналам (краткая версия)
                if details.get('private'):
                    text += f"\n🔒 <b>Приватных каналов:</b> {len(details['private'])}\n"
                
                # Детали по заявкам (краткая версия)
                if details.get('pending_approval'):
                    text += f"⏳ <b>Заявки поданы:</b> {len(details['pending_approval'])}\n"
                
                # Детали по ошибкам (краткая версия)
                if details.get('errors'):
                    text += f"❌ <b>Других ошибок:</b> {len(details['errors'])}\n"
                
                # Создаём клавиатуру с кнопками
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                
                # Кнопка "Подробнее" если есть ошибки/приватные/заявки
                if details.get('private') or details.get('errors') or details.get('pending_approval'):
                    # Сохраняем детали в FSM state для последующего показа
                    await state.update_data(join_errors_details=details)
                    
                    builder.button(text="📋 Подробнее об ошибках", callback_data="chats:join_errors")
                
                builder.button(text="🔙 Назад", callback_data="menu:chats")
                builder.adjust(1)
                
                await callback.message.edit_text(
                    text,
                    reply_markup=builder.as_markup()
                )
            else:
                error_text = response.text if response.text else "Unknown error"
                await callback.message.edit_text(
                    f"❌ <b>Ошибка автоподписки</b>\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_text[:200]}",
                    reply_markup=get_chats_menu_keyboard()
                )
                
    except httpx.TimeoutException:
        await callback.message.edit_text(
            "❌ <b>Timeout</b>\n\n"
            "Процесс подписки занял слишком много времени.\n"
            "Возможно, некоторые каналы уже добавлены.\n"
            "Попробуйте ещё раз через несколько минут.",
            reply_markup=get_chats_menu_keyboard()
        )
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ <b>Непредвиденная ошибка</b>\n\n"
            f"{str(e)[:200]}",
            reply_markup=get_chats_menu_keyboard()
        )


## Callback список чатов (с пагинацией)
@router.callback_query(F.data == "chats:list", OperatorFilter())
async def callback_list_chats(callback: CallbackQuery):
    """
    Показывает список чатов через callback (страница 1).
    """
    await show_chats_page(callback, page=1)


@router.callback_query(F.data.startswith("chats:page:"), OperatorFilter())
async def callback_chats_page(callback: CallbackQuery):
    """
    ## Навигация по страницам списка чатов
    """
    page = int(callback.data.split(":")[2])
    await show_chats_page(callback, page=page)


async def show_chats_page(callback: CallbackQuery, page: int):
    """
    ## Отображение списка чатов с пагинацией
    
    Args:
        callback: Callback запрос
        page: Номер страницы (начиная с 1)
    """
    async with get_session() as session:
        chats = await get_all_chats(session, enabled_only=False, exclude_blacklisted=False)
    
    if not chats:
        await callback.message.edit_text(
            "📭 <b>Список чатов пуст</b>\n\n"
            "Добавьте чаты для мониторинга.",
            reply_markup=get_chats_menu_keyboard()
        )
        await callback.answer()
        return
    
    # Пагинация
    total_chats = len(chats)
    total_pages = (total_chats + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE  # Округление вверх
    page = max(1, min(page, total_pages))  # Ограничиваем диапазон
    
    start_idx = (page - 1) * CHATS_PER_PAGE
    end_idx = start_idx + CHATS_PER_PAGE
    page_chats = chats[start_idx:end_idx]
    
    # Формируем текст списка
    text_lines = [
        f"💬 <b>Список чатов</b>\n",
        f"📄 Страница {page}/{total_pages} | Всего: {total_chats}\n"
    ]
    
    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        whitelist_icon = "⚪" if chat.is_whitelisted else ""
        blacklist_icon = "⚫" if chat.is_blacklisted else ""
        
        text_lines.append(
            f"{status_icon} {whitelist_icon}{blacklist_icon} "
            f"{hbold(chat.title)}\n"
            f"   ID: #{chat.id} | Тип: {chat.type}"
        )
        text_lines.append("")
    
    text = "\n".join(text_lines)
    
    # Создаём клавиатуру с кнопками чатов
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        builder.button(
            text=f"{status_icon} {chat.title[:25]}",
            callback_data=f"chat:view:{chat.id}"
        )
    
    # Кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(("◀️ Назад", f"chats:page:{page-1}"))
    if page < total_pages:
        nav_buttons.append(("Вперёд ▶️", f"chats:page:{page+1}"))
    
    for text_btn, callback_data in nav_buttons:
        builder.button(text=text_btn, callback_data=callback_data)
    
    builder.button(text="🔙 В меню чатов", callback_data="menu:chats")
    
    # Adjust: по 1 кнопке чата в ряд, навигация в один ряд
    builder.adjust(1, *(1 for _ in page_chats), len(nav_buttons), 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


## Callback просмотра конкретного чата
@router.callback_query(F.data.startswith("chat:view:"), OperatorFilter())
async def callback_view_chat(callback: CallbackQuery):
    """
    Показывает подробную информацию о чате.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
    
    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    
    # Формируем текст карточки чата
    text = (
        f"💬 <b>{chat.title}</b>\n\n"
        f"🆔 <b>Telegram ID:</b> {hcode(str(chat.tg_chat_id))}\n"
        f"🆔 <b>ID в БД:</b> #{chat.id}\n"
        f"📂 <b>Тип:</b> {chat.type}\n"
    )
    
    if chat.username:
        text += f"🔗 <b>Username:</b> @{chat.username}\n"
    
    text += (
        f"🔢 <b>Приоритет:</b> {chat.priority}\n"
        f"✅ <b>Мониторинг:</b> {'Включён 🟢' if chat.enabled else 'Выключен 🔴'}\n"
        f"⚪ <b>Белый список:</b> {'Да' if chat.is_whitelisted else 'Нет'}\n"
        f"⚫ <b>Чёрный список:</b> {'Да' if chat.is_blacklisted else 'Нет'}\n"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
    )
    await callback.answer()


## Callback включения чата
@router.callback_query(F.data.startswith("chat:enable:"), OperatorFilter())
async def callback_enable_chat(callback: CallbackQuery):
    """
    Включает мониторинг чата.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        success = await update_chat_status(session, chat_id, enabled=True)
        await session.commit()
        
        if success:
            chat = await get_chat_by_id(session, chat_id)
            await callback.answer("✅ Мониторинг включён", show_alert=False)
            
            # Обновляем карточку
            text = (
                f"💬 <b>{chat.title}</b>\n\n"
                f"✅ Мониторинг чата включён."
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_chat_actions_keyboard(chat.id, True)
            )
        else:
            await callback.answer("❌ Ошибка при включении", show_alert=True)


## Callback выключения чата
@router.callback_query(F.data.startswith("chat:disable:"), OperatorFilter())
async def callback_disable_chat(callback: CallbackQuery):
    """
    Выключает мониторинг чата.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        success = await update_chat_status(session, chat_id, enabled=False)
        await session.commit()
        
        if success:
            chat = await get_chat_by_id(session, chat_id)
            await callback.answer("🔴 Мониторинг выключен", show_alert=False)
            
            text = (
                f"💬 <b>{chat.title}</b>\n\n"
                f"🔴 Мониторинг чата выключен."
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_chat_actions_keyboard(chat.id, False)
            )
        else:
            await callback.answer("❌ Ошибка при выключении", show_alert=True)


## Callback добавления в белый список
@router.callback_query(F.data.startswith("chat:whitelist:"), OperatorFilter())
async def callback_whitelist_chat(callback: CallbackQuery):
    """
    Добавляет чат в белый список.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
        
        # Переключаем статус белого списка
        new_status = not chat.is_whitelisted
        success = await update_chat_whitelist(session, chat_id, new_status)
        await session.commit()
        
        if success:
            status_text = "добавлен в" if new_status else "убран из"
            await callback.answer(f"⚪ Чат {status_text} белого списка", show_alert=False)
            
            # Перезагружаем чат
            chat = await get_chat_by_id(session, chat_id)
            await callback.message.edit_text(
                f"💬 <b>{chat.title}</b>\n\n"
                f"⚪ Статус белого списка изменён.",
                reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
            )
        else:
            await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)


## Callback добавления в чёрный список
@router.callback_query(F.data.startswith("chat:blacklist:"), OperatorFilter())
async def callback_blacklist_chat(callback: CallbackQuery):
    """
    Добавляет чат в чёрный список.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
        
        # Переключаем статус чёрного списка
        new_status = not chat.is_blacklisted
        success = await update_chat_blacklist(session, chat_id, new_status)
        await session.commit()
        
        if success:
            status_text = "добавлен в" if new_status else "убран из"
            await callback.answer(f"⚫ Чат {status_text} чёрного списка", show_alert=False)
            
            # Перезагружаем чат
            chat = await get_chat_by_id(session, chat_id)
            await callback.message.edit_text(
                f"💬 <b>{chat.title}</b>\n\n"
                f"⚫ Статус чёрного списка изменён.",
                reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
            )
        else:
            await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)


## Callback удаления чата
@router.callback_query(F.data.startswith("chat:delete:"), OperatorFilter())
async def callback_delete_chat(callback: CallbackQuery):
    """
    Запрашивает подтверждение удаления чата.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
    
    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"⚠️ <b>Подтвердите удаление</b>\n\n"
        f"Вы действительно хотите удалить чат {hbold(chat.title)}?\n\n"
        f"❗ Все связанные лиды также будут удалены.",
        reply_markup=get_confirmation_keyboard("delete", chat_id, "chat")
    )
    await callback.answer()


## Callback подтверждения удаления
@router.callback_query(F.data.startswith("chat:delete_confirm:"), OperatorFilter())
async def callback_delete_chat_confirm(callback: CallbackQuery):
    """
    Подтверждает и выполняет удаление чата.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
        chat_title = chat.title if chat else "Неизвестный чат"
        
        success = await delete_chat(session, chat_id)
        await session.commit()
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Чат удалён</b>\n\n"
            f"Чат {hbold(chat_title)} успешно удалён из мониторинга.",
            reply_markup=get_chats_menu_keyboard()
        )
        await callback.answer("🗑 Чат удалён")
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


## Callback отмены действия
@router.callback_query(F.data.startswith("chat:cancel:"), OperatorFilter())
async def callback_cancel_chat_action(callback: CallbackQuery):
    """
    Отменяет действие и возвращает к карточке чата.
    """
    chat_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
    
    if chat:
        text = (
            f"💬 <b>{chat.title}</b>\n\n"
            f"Действие отменено."
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
        )
    
    await callback.answer("Действие отменено")


## Обработка текстового ввода Chat ID или username
## Обработка Chat ID или username (исключаем команды начинающиеся с /)
@router.message(AddChatStates.waiting_for_chat_forward, OperatorFilter(), F.text, ~F.text.startswith("/"))
async def process_chat_id_or_username(message: Message, state: FSMContext):
    """
    Обрабатывает добавление чата по Chat ID или username через Lead Listener API.
    """
    import httpx
    from config import settings
    
    text = message.text.strip()
    
    # Проверяем: это ссылка, Chat ID или username?
    is_link = 't.me/' in text or 'telegram.me/' in text
    is_chat_id = text.startswith('-')
    is_username = text.startswith('@')
    
    if not is_link and not is_chat_id and not is_username:
        # Может быть username без @ или некорректный ввод
        if text.isdigit() or (text.startswith('-') and text[1:].isdigit()):
            # Это похоже на ID, но без минуса
            await message.answer(
                "❌ <b>Неверный формат Chat ID</b>\n\n"
                "Chat ID должен начинаться с минуса (например: <code>-1001234567890</code>)\n\n"
                "Или отправьте username канала/группы:\n"
                "• С @: <code>@pythonru</code>\n"
                "• Без @: <code>pythonru</code>\n\n"
                "Попробуйте ещё раз или отправьте /cancel."
            )
            return
        else:
            # Вероятно username без @ - добавим
            text = f"@{text}"
            await message.answer(f"💡 Интерпретирую как username: {hcode(text)}")
    
    await message.answer(
        "⏳ <b>Получаю информацию о чате...</b>\n\n"
        "Это может занять несколько секунд."
    )
    
    try:
        # Формируем URL Lead Listener API (старый способ, но с портом из env)
        port = str(settings.lead_listener_api_port)
        lead_listener_url = settings.admin_bot_api_url.replace('admin_bot', 'lead_listener').replace('8000', port)
        api_url = f"{lead_listener_url}/api/get_chat_info"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                json={"identifier": text}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Проверяем, не добавлен ли уже этот чат
                async with get_session() as session:
                    existing_chat = await get_chat_by_tg_id(session, data['chat_id'])
                    
                    if existing_chat:
                        await message.answer(
                            f"⚠️ <b>Чат уже добавлен</b>\n\n"
                            f"📝 <b>Название:</b> {existing_chat.title}\n"
                            f"🆔 <b>ID:</b> #{existing_chat.id}\n\n"
                            "Используйте /list_chats для просмотра.",
                            reply_markup=get_chats_menu_keyboard()
                        )
                        await state.clear()
                        return
                    
                    # Определяем тип чата
                    chat_type = ChatType.GROUP.value
                    if data['type'] == 'channel':
                        chat_type = ChatType.CHANNEL.value
                    elif data['type'] == 'supergroup':
                        chat_type = ChatType.SUPERGROUP.value
                    
                    # Создаём чат в БД
                    new_chat = await create_chat(
                        session,
                        tg_chat_id=data['chat_id'],
                        title=data['title'],
                        chat_type=chat_type,
                        username=data.get('username'),
                        priority=1,
                        enabled=True
                    )
                    await session.commit()
                
                await message.answer(
                    f"✅ <b>Чат успешно добавлен!</b>\n\n"
                    f"📝 <b>Название:</b> {new_chat.title}\n"
                    f"🆔 <b>ID чата:</b> {hcode(str(new_chat.tg_chat_id))}\n"
                    f"📂 <b>Тип:</b> {new_chat.type}\n"
                    f"🔢 <b>Приоритет:</b> {new_chat.priority}\n"
                    f"✅ <b>Мониторинг:</b> Включён\n\n"
                    "Чат будет отслеживаться на наличие лидов.",
                    reply_markup=get_chats_menu_keyboard()
                )
                
                await state.clear()
                
            elif response.status_code == 404:
                await message.answer(
                    "❌ <b>Чат не найден</b>\n\n"
                    "Возможные причины:\n"
                    "• Неверный Chat ID или username\n"
                    "• Рабочий аккаунт не состоит в этом чате\n"
                    "• Чат является приватным и недоступен\n\n"
                    "💡 <b>Что делать:</b>\n"
                    "1. Проверьте правильность ID/username\n"
                    "2. Убедитесь, что рабочий аккаунт состоит в чате\n"
                    "3. Попробуйте переслать сообщение из публичного канала\n\n"
                    "Попробуйте ещё раз или отправьте /cancel."
                )
                
            else:
                error_text = response.text if response.text else "Unknown error"
                await message.answer(
                    f"❌ <b>Ошибка получения информации</b>\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_text[:200]}\n\n"
                    "Попробуйте ещё раз или отправьте /cancel."
                )
                
    except httpx.TimeoutException:
        await message.answer(
            "❌ <b>Timeout</b>\n\n"
            "Превышено время ожидания ответа от Lead Listener.\n"
            "Попробуйте ещё раз через несколько секунд."
        )
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Непредвиденная ошибка</b>\n\n"
            f"{str(e)[:200]}\n\n"
            "Попробуйте ещё раз или отправьте /cancel."
        )


## Обработчик кнопки "Подробнее об ошибках"
@router.callback_query(F.data == "chats:join_errors", OperatorFilter())
async def callback_show_join_errors(callback: CallbackQuery, state: FSMContext):
    """
    ## Показать подробную информацию об ошибках автоподписки
    """
    # Получаем сохранённые детали из state
    data = await state.get_data()
    details = data.get('join_errors_details', {})
    
    if not details:
        await callback.answer("❌ Нет данных об ошибках", show_alert=True)
        return
    
    # Формируем подробный отчёт
    text_lines = ["📋 <b>Подробный отчёт об ошибках</b>\n"]
    
    # Приватные каналы (с ссылками)
    private_channels = details.get('private', [])
    if private_channels:
        text_lines.append(f"🔒 <b>Приватные каналы ({len(private_channels)}):</b>")
        text_lines.append("<i>Требуется invite-ссылка для вступления</i>\n")
        
        for item in private_channels:
            chat_title = item.get('chat', 'Без названия')
            username = item.get('username', '')
            
            if username:
                # Создаём кликабельную ссылку
                link = f"https://t.me/{username}"
                text_lines.append(f"• <a href='{link}'>{chat_title}</a>")
            else:
                text_lines.append(f"• {chat_title} (нет username)")
        
        text_lines.append("\n💡 <i>Вступите в эти каналы вручную, затем запустите автоподписку снова</i>\n")
    
    # Заявки на одобрение (с ссылками)
    pending_approval = details.get('pending_approval', [])
    if pending_approval:
        text_lines.append(f"⏳ <b>Ожидают одобрения ({len(pending_approval)}):</b>")
        text_lines.append("<i>Заявки поданы автоматически, ждём одобрения админов</i>\n")
        
        for item in pending_approval:
            chat_title = item.get('chat', 'Без названия')
            username = item.get('username', '')
            status = item.get('status', 'unknown')
            
            status_emoji = "📝" if status == "request_sent" else "⏳"
            status_text = "заявка подана" if status == "request_sent" else "ожидает"
            
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"{status_emoji} <a href='{link}'>{chat_title}</a> ({status_text})")
            else:
                text_lines.append(f"{status_emoji} {chat_title} ({status_text}, нет username)")
        
        text_lines.append("\n💡 <i>После одобрения запустите автоподписку снова — чаты автоматически добавятся в мониторинг!</i>\n")
    
    # Другие ошибки (с ссылками)
    errors = details.get('errors', [])
    if errors:
        text_lines.append(f"\n❌ <b>Другие ошибки ({len(errors)}):</b>\n")
        
        for item in errors[:10]:  # Показываем первые 10
            chat_title = item.get('chat', 'Без названия')
            username = item.get('username', '')
            error_msg = item.get('error', 'Unknown')
            
            # Создаём кликабельную ссылку если есть username
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"• <a href='{link}'>{chat_title}</a>")
            else:
                text_lines.append(f"• <b>{chat_title}</b> (нет username)")
            
            text_lines.append(f"  <i>{error_msg[:100]}</i>\n")
        
        if len(errors) > 10:
            text_lines.append(f"<i>...и ещё {len(errors) - 10} ошибок</i>")
    
    # FloodWait (с ссылками)
    flood_wait = details.get('flood_wait', [])
    if flood_wait:
        text_lines.append(f"\n⏳ <b>FloodWait ({len(flood_wait)}):</b>")
        text_lines.append("<i>Telegram ограничил скорость подписок</i>\n")
        
        for item in flood_wait[:5]:
            chat_title = item.get('chat', 'Без названия')
            username = item.get('username', '')
            wait_seconds = item.get('wait_seconds', 0)
            
            # Создаём кликабельную ссылку если есть username
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"• <a href='{link}'>{chat_title}</a> (ждать {wait_seconds}с)")
            else:
                text_lines.append(f"• {chat_title} (ждать {wait_seconds}с, нет username)")
    
    text = "\n".join(text_lines)
    
    # Кнопка назад
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="menu:chats")
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        disable_web_page_preview=True
    )
    await callback.answer()


## Обработка отмены во время добавления чата
@router.message(Command("cancel"), AddChatStates())
async def cancel_add_chat(message: Message, state: FSMContext):
    """
    Отменяет процесс добавления чата.
    """
    await state.clear()
    await message.answer(
        "❌ Добавление чата отменено.",
        reply_markup=get_chats_menu_keyboard()
    )

