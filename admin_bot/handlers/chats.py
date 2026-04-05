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
from shared.locales import t


router = Router(name="chats_router")

# Константы
CHATS_PER_PAGE = 10


## Обработка кнопки "Добавить чат"
@router.callback_query(F.data == "chats:add", OperatorFilter())
async def callback_add_chat(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    Начало процесса добавления чата через кнопку.
    """
    await state.set_state(AddChatStates.waiting_for_chat_forward)

    await callback.message.answer(
        t("chats.add_title", lang) + t("chats.add_methods_btn", lang)
    )

    await callback.answer()


## Команда /add_chat
@router.message(Command("add_chat"), OperatorFilter())
async def cmd_add_chat(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Начало процесса добавления чата через команду.
    """
    await state.set_state(AddChatStates.waiting_for_chat_forward)

    await message.answer(
        t("chats.add_title", lang) + t("chats.add_methods_cmd", lang)
    )


## Обработка пересланного сообщения ОТ ПОЛЬЗОВАТЕЛЯ (не подходит)
@router.message(AddChatStates.waiting_for_chat_forward, OperatorFilter(), F.forward_from)
async def process_user_forward_error(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает ошибку когда пользователь переслал сообщение от другого пользователя.
    """
    await message.answer(t("chats.forward_user_error", lang))


## Обработка пересланного сообщения для добавления чата
@router.message(AddChatStates.waiting_for_chat_forward, OperatorFilter(), F.forward_from_chat)
async def process_chat_forward(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает пересланное сообщение и извлекает информацию о чате.
    """
    chat = message.forward_from_chat

    if not chat:
        await message.answer(t("chats.forward_error", lang))
        return

    async with get_session() as session:
        existing_chat = await get_chat_by_tg_id(session, chat.id)

        if existing_chat:
            await message.answer(
                t("chats.already_added", lang,
                  title=hbold(chat.title),
                  id=existing_chat.id)
            )
            await state.clear()
            return

        chat_type = ChatType.GROUP.value
        if chat.type == "channel":
            chat_type = ChatType.CHANNEL.value
        elif chat.type == "supergroup":
            chat_type = ChatType.SUPERGROUP.value

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
        t("chats.added_ok", lang,
          title=new_chat.title,
          tg_chat_id=hcode(str(new_chat.tg_chat_id)),
          type=new_chat.type,
          priority=new_chat.priority),
        reply_markup=get_chats_menu_keyboard(lang)
    )

    await state.clear()


## Команда /list_chats (с пагинацией)
@router.message(Command("list_chats"), OperatorFilter())
async def cmd_list_chats(message: Message, lang: str = "ru"):
    """
    Показывает список всех добавленных чатов (первая страница).
    """
    async with get_session() as session:
        chats = await get_all_chats(session, enabled_only=False, exclude_blacklisted=False)

    if not chats:
        await message.answer(
            t("chats.empty_cmd", lang),
            reply_markup=get_chats_menu_keyboard(lang)
        )
        return

    total_chats = len(chats)
    total_pages = (total_chats + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE
    page = 1
    page_chats = chats[:CHATS_PER_PAGE]

    text_lines = [
        t("chats.list_title", lang),
        t("chats.list_page", lang, page=page, total=total_pages, count=total_chats) + "\n"
    ]

    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        whitelist_icon = "⚪" if chat.is_whitelisted else ""
        blacklist_icon = "⚫" if chat.is_blacklisted else ""

        text_lines.append(
            f"{status_icon} {whitelist_icon}{blacklist_icon} "
            f"{hbold(chat.title)}\n"
            f"   ID: #{chat.id} | {t('chats.card_type', lang, type=chat.type).strip()}"
        )
        text_lines.append("")

    text = "\n".join(text_lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        builder.button(
            text=f"{status_icon} {chat.title[:25]}",
            callback_data=f"chat:view:{chat.id}"
        )

    if total_pages > 1:
        builder.button(text=t("common.forward", lang), callback_data="chats:page:2")

    builder.button(text=t("chats.btn_add_chat", lang), callback_data="chats:add")
    builder.button(text=t("menu.back", lang), callback_data="menu:main")

    adjust_pattern = [1] * len(page_chats)
    if total_pages > 1:
        adjust_pattern.append(1)
    adjust_pattern.append(2)
    builder.adjust(*adjust_pattern)

    await message.answer(text, reply_markup=builder.as_markup())


## Callback меню чатов
@router.callback_query(F.data == "menu:chats", OperatorFilter())
async def callback_chats_menu(callback: CallbackQuery, lang: str = "ru"):
    """
    Обработчик callback меню чатов.
    """
    async with get_session() as session:
        all_chats = await get_all_chats(session)
        enabled_count = sum(1 for c in all_chats if c.enabled)
        total_count = len(all_chats)

    await callback.message.edit_text(
        t("chats.menu_title", lang, total=total_count, enabled=enabled_count),
        reply_markup=get_chats_menu_keyboard(lang)
    )
    await callback.answer()


## Обработка кнопки "Чёрный список"
@router.callback_query(F.data == "chats:blacklist", OperatorFilter())
async def callback_chats_blacklist(callback: CallbackQuery, lang: str = "ru"):
    """Показывает чаты из чёрного списка."""
    async with get_session() as session:
        chats = await get_all_chats(session, enabled_only=False, exclude_blacklisted=False)
        blacklisted = [c for c in chats if c.is_blacklisted]

        text = t("chats.blacklist_title", lang)
        if not blacklisted:
            text += t("chats.blacklist_empty", lang)
        else:
            text += t("chats.blacklist_count", lang, count=len(blacklisted))
            for chat in blacklisted[:10]:
                text += f"<b>{chat.title}</b> (<code>{chat.tg_chat_id}</code>)\n"
            if len(blacklisted) > 10:
                text += t("chats.blacklist_more", lang, count=len(blacklisted) - 10)

        await callback.message.edit_text(text, reply_markup=get_chats_menu_keyboard(lang))
    await callback.answer()


## Автоподписка на все чаты
@router.callback_query(F.data == "chats:join_all", OperatorFilter())
async def callback_join_all_chats(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Подписка monitor-аккаунта на все активные чаты
    Reply-аккаунты не вступают в чаты -- только мониторинг.
    """
    import httpx
    from config import settings

    await callback.answer(t("chats.join_starting", lang), show_alert=False)

    await callback.message.edit_text(
        t("chats.join_in_progress", lang),
        reply_markup=None
    )

    try:
        port = str(settings.lead_listener_api_port)
        lead_listener_url = settings.admin_bot_api_url.replace('admin_bot', 'lead_listener').replace('8000', port)
        api_url = f"{lead_listener_url}/api/join_all_chats"

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(api_url)

            if response.status_code == 200:
                data = response.json()
                results = data.get('results', {})
                details = data.get('details', {})

                text = t("chats.join_done", lang) + t("chats.join_stats", lang)
                text += t("chats.join_success", lang, count=results.get('success', 0))
                text += t("chats.join_already", lang, count=results.get('already_joined', 0))

                if results.get('private', 0) > 0:
                    text += t("chats.join_private", lang, count=results.get('private', 0))
                if results.get('flood_wait', 0) > 0:
                    text += t("chats.join_flood", lang, count=results.get('flood_wait', 0))
                if results.get('pending_approval', 0) > 0:
                    text += t("chats.join_pending", lang, count=results.get('pending_approval', 0))
                if results.get('errors', 0) > 0:
                    text += t("chats.join_errors", lang, count=results.get('errors', 0))

                if details.get('private'):
                    text += t("chats.join_private_label", lang, count=len(details['private']))
                if details.get('pending_approval'):
                    text += t("chats.join_pending_label", lang, count=len(details['pending_approval']))
                if details.get('errors'):
                    text += t("chats.join_errors_label", lang, count=len(details['errors']))

                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()

                if details.get('private') or details.get('errors') or details.get('pending_approval'):
                    await state.update_data(join_errors_details=details)
                    builder.button(text=t("chats.join_details_btn", lang), callback_data="chats:join_errors")

                builder.button(text=t("menu.back", lang), callback_data="menu:chats")
                builder.adjust(1)

                await callback.message.edit_text(
                    text,
                    reply_markup=builder.as_markup()
                )
            else:
                error_text = response.text if response.text else "Unknown error"
                await callback.message.edit_text(
                    t("chats.join_api_error", lang, status=response.status_code, error=error_text[:200]),
                    reply_markup=get_chats_menu_keyboard(lang)
                )

    except httpx.TimeoutException:
        await callback.message.edit_text(
            t("chats.join_timeout", lang),
            reply_markup=get_chats_menu_keyboard(lang)
        )

    except Exception as e:
        await callback.message.edit_text(
            t("chats.join_unexpected", lang, error=str(e)[:200]),
            reply_markup=get_chats_menu_keyboard(lang)
        )


## Callback список чатов (с пагинацией)
@router.callback_query(F.data == "chats:list", OperatorFilter())
async def callback_list_chats(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает список чатов через callback (страница 1).
    """
    await show_chats_page(callback, page=1, lang=lang)


@router.callback_query(F.data.startswith("chats:page:"), OperatorFilter())
async def callback_chats_page(callback: CallbackQuery, lang: str = "ru"):
    """
    ## Навигация по страницам списка чатов
    """
    page = int(callback.data.split(":")[2])
    await show_chats_page(callback, page=page, lang=lang)


async def show_chats_page(callback: CallbackQuery, page: int, lang: str = "ru"):
    """
    ## Отображение списка чатов с пагинацией
    """
    async with get_session() as session:
        chats = await get_all_chats(session, enabled_only=False, exclude_blacklisted=False)

    if not chats:
        await callback.message.edit_text(
            t("chats.empty", lang),
            reply_markup=get_chats_menu_keyboard(lang)
        )
        await callback.answer()
        return

    total_chats = len(chats)
    total_pages = (total_chats + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * CHATS_PER_PAGE
    end_idx = start_idx + CHATS_PER_PAGE
    page_chats = chats[start_idx:end_idx]

    text_lines = [
        t("chats.list_title", lang),
        t("chats.list_page", lang, page=page, total=total_pages, count=total_chats) + "\n"
    ]

    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        whitelist_icon = "⚪" if chat.is_whitelisted else ""
        blacklist_icon = "⚫" if chat.is_blacklisted else ""

        text_lines.append(
            f"{status_icon} {whitelist_icon}{blacklist_icon} "
            f"{hbold(chat.title)}\n"
            f"   ID: #{chat.id} | {t('chats.card_type', lang, type=chat.type).strip()}"
        )
        text_lines.append("")

    text = "\n".join(text_lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for chat in page_chats:
        status_icon = "🟢" if chat.enabled else "🔴"
        builder.button(
            text=f"{status_icon} {chat.title[:25]}",
            callback_data=f"chat:view:{chat.id}"
        )

    nav_buttons = []
    if page > 1:
        nav_buttons.append((t("common.prev", lang), f"chats:page:{page-1}"))
    if page < total_pages:
        nav_buttons.append((t("common.forward", lang), f"chats:page:{page+1}"))

    for text_btn, callback_data in nav_buttons:
        builder.button(text=text_btn, callback_data=callback_data)

    builder.button(text=t("chats.btn_back_chats", lang), callback_data="menu:chats")

    builder.adjust(1, *(1 for _ in page_chats), len(nav_buttons), 1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


## Callback просмотра конкретного чата
@router.callback_query(F.data.startswith("chat:view:"), OperatorFilter())
async def callback_view_chat(callback: CallbackQuery, lang: str = "ru"):
    """
    Показывает подробную информацию о чате.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)

    if not chat:
        await callback.answer(t("chats.not_found", lang), show_alert=True)
        return

    text = t("chats.card_title", lang, title=chat.title)
    text += t("chats.card_tg_id", lang, tg_id=hcode(str(chat.tg_chat_id)))
    text += t("chats.card_db_id", lang, id=chat.id)
    text += t("chats.card_type", lang, type=chat.type)

    if chat.username:
        text += t("chats.card_username", lang, username=chat.username)

    text += t("chats.card_priority", lang, priority=chat.priority)
    text += t("chats.card_monitoring_on", lang) if chat.enabled else t("chats.card_monitoring_off", lang)
    text += t("chats.card_whitelist", lang, status=t("chats.yes", lang) if chat.is_whitelisted else t("chats.no", lang))
    text += t("chats.card_blacklist", lang, status=t("chats.yes", lang) if chat.is_blacklisted else t("chats.no", lang))

    await callback.message.edit_text(
        text,
        reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
    )
    await callback.answer()


## Callback включения чата
@router.callback_query(F.data.startswith("chat:enable:"), OperatorFilter())
async def callback_enable_chat(callback: CallbackQuery, lang: str = "ru"):
    """
    Включает мониторинг чата.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await update_chat_status(session, chat_id, enabled=True)
        await session.commit()

        if success:
            chat = await get_chat_by_id(session, chat_id)
            await callback.answer(t("chats.monitoring_on", lang), show_alert=False)

            await callback.message.edit_text(
                t("chats.monitoring_on_text", lang, title=chat.title),
                reply_markup=get_chat_actions_keyboard(chat.id, True)
            )
        else:
            await callback.answer(t("chats.enable_error", lang), show_alert=True)


## Callback выключения чата
@router.callback_query(F.data.startswith("chat:disable:"), OperatorFilter())
async def callback_disable_chat(callback: CallbackQuery, lang: str = "ru"):
    """
    Выключает мониторинг чата.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        success = await update_chat_status(session, chat_id, enabled=False)
        await session.commit()

        if success:
            chat = await get_chat_by_id(session, chat_id)
            await callback.answer(t("chats.monitoring_off", lang), show_alert=False)

            await callback.message.edit_text(
                t("chats.monitoring_off_text", lang, title=chat.title),
                reply_markup=get_chat_actions_keyboard(chat.id, False)
            )
        else:
            await callback.answer(t("chats.disable_error", lang), show_alert=True)


## Callback добавления в белый список
@router.callback_query(F.data.startswith("chat:whitelist:"), OperatorFilter())
async def callback_whitelist_chat(callback: CallbackQuery, lang: str = "ru"):
    """
    Добавляет чат в белый список.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)

        new_status = not chat.is_whitelisted
        success = await update_chat_whitelist(session, chat_id, new_status)
        await session.commit()

        if success:
            toast = t("chats.whitelist_added", lang) if new_status else t("chats.whitelist_removed", lang)
            await callback.answer(toast, show_alert=False)

            chat = await get_chat_by_id(session, chat_id)
            await callback.message.edit_text(
                t("chats.whitelist_changed", lang, title=chat.title),
                reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
            )
        else:
            await callback.answer(t("chats.whitelist_error", lang), show_alert=True)


## Callback добавления в чёрный список
@router.callback_query(F.data.startswith("chat:blacklist:"), OperatorFilter())
async def callback_blacklist_chat(callback: CallbackQuery, lang: str = "ru"):
    """
    Добавляет чат в чёрный список.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)

        new_status = not chat.is_blacklisted
        success = await update_chat_blacklist(session, chat_id, new_status)
        await session.commit()

        if success:
            toast = t("chats.blacklist_added", lang) if new_status else t("chats.blacklist_removed", lang)
            await callback.answer(toast, show_alert=False)

            chat = await get_chat_by_id(session, chat_id)
            await callback.message.edit_text(
                t("chats.blacklist_changed", lang, title=chat.title),
                reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
            )
        else:
            await callback.answer(t("chats.blacklist_error", lang), show_alert=True)


## Callback удаления чата
@router.callback_query(F.data.startswith("chat:delete:"), OperatorFilter())
async def callback_delete_chat(callback: CallbackQuery, lang: str = "ru"):
    """
    Запрашивает подтверждение удаления чата.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)

    if not chat:
        await callback.answer(t("chats.not_found", lang), show_alert=True)
        return

    await callback.message.edit_text(
        t("chats.delete_confirm", lang, title=hbold(chat.title)),
        reply_markup=get_confirmation_keyboard("delete", chat_id, "chat")
    )
    await callback.answer()


## Callback подтверждения удаления
@router.callback_query(F.data.startswith("chat:delete_confirm:"), OperatorFilter())
async def callback_delete_chat_confirm(callback: CallbackQuery, lang: str = "ru"):
    """
    Подтверждает и выполняет удаление чата.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)
        chat_title = chat.title if chat else "?"

        success = await delete_chat(session, chat_id)
        await session.commit()

    if success:
        await callback.message.edit_text(
            t("chats.deleted", lang, title=hbold(chat_title)),
            reply_markup=get_chats_menu_keyboard(lang)
        )
        await callback.answer(t("chats.delete_ok_toast", lang))
    else:
        await callback.answer(t("chats.delete_error", lang), show_alert=True)


## Callback отмены действия
@router.callback_query(F.data.startswith("chat:cancel:"), OperatorFilter())
async def callback_cancel_chat_action(callback: CallbackQuery, lang: str = "ru"):
    """
    Отменяет действие и возвращает к карточке чата.
    """
    chat_id = int(callback.data.split(":")[2])

    async with get_session() as session:
        chat = await get_chat_by_id(session, chat_id)

    if chat:
        await callback.message.edit_text(
            t("chats.action_cancelled_text", lang, title=chat.title),
            reply_markup=get_chat_actions_keyboard(chat.id, chat.enabled)
        )

    await callback.answer(t("chats.action_cancelled", lang))


## Обработка текстового ввода Chat ID или username
## Обработка Chat ID или username (исключаем команды начинающиеся с /)
@router.message(AddChatStates.waiting_for_chat_forward, OperatorFilter(), F.text, ~F.text.startswith("/"))
async def process_chat_id_or_username(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Обрабатывает добавление чата по Chat ID или username через Lead Listener API.
    """
    import httpx
    from config import settings

    text = message.text.strip()

    is_link = 't.me/' in text or 'telegram.me/' in text
    is_chat_id = text.startswith('-')
    is_username = text.startswith('@')

    if not is_link and not is_chat_id and not is_username:
        if text.isdigit() or (text.startswith('-') and text[1:].isdigit()):
            await message.answer(t("chats.bad_chat_id", lang))
            return
        else:
            text = f"@{text}"
            await message.answer(t("chats.interpret_username", lang, username=hcode(text)))

    await message.answer(t("chats.getting_info", lang))

    try:
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

                async with get_session() as session:
                    existing_chat = await get_chat_by_tg_id(session, data['chat_id'])

                    if existing_chat:
                        await message.answer(
                            t("chats.already_added_info", lang,
                              title=existing_chat.title,
                              id=existing_chat.id),
                            reply_markup=get_chats_menu_keyboard(lang)
                        )
                        await state.clear()
                        return

                    chat_type = ChatType.GROUP.value
                    if data['type'] == 'channel':
                        chat_type = ChatType.CHANNEL.value
                    elif data['type'] == 'supergroup':
                        chat_type = ChatType.SUPERGROUP.value

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
                    t("chats.added_ok", lang,
                      title=new_chat.title,
                      tg_chat_id=hcode(str(new_chat.tg_chat_id)),
                      type=new_chat.type,
                      priority=new_chat.priority),
                    reply_markup=get_chats_menu_keyboard(lang)
                )

                await state.clear()

            elif response.status_code == 404:
                await message.answer(
                    t("chats.not_found", lang) + "\n\n"
                    "Возможные причины:\n"
                    "• Неверный Chat ID или username\n"
                    "• Рабочий аккаунт не состоит в этом чате\n"
                    "• Чат является приватным и недоступен"
                )

            else:
                error_text = response.text if response.text else "Unknown error"
                await message.answer(
                    t("chats.join_api_error", lang, status=response.status_code, error=error_text[:200])
                )

    except httpx.TimeoutException:
        await message.answer(t("chats.join_timeout", lang))

    except Exception as e:
        await message.answer(
            t("chats.join_unexpected", lang, error=str(e)[:200])
        )


## Обработчик кнопки "Подробнее об ошибках"
@router.callback_query(F.data == "chats:join_errors", OperatorFilter())
async def callback_show_join_errors(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """
    ## Показать подробную информацию об ошибках автоподписки
    """
    data = await state.get_data()
    details = data.get('join_errors_details', {})

    if not details:
        await callback.answer("❌", show_alert=True)
        return

    # Формируем подробный отчёт (этот текст слишком специфичен для локалей -- оставляем inline)
    text_lines = ["📋 <b>Подробный отчёт</b>\n"]

    private_channels = details.get('private', [])
    if private_channels:
        text_lines.append(f"🔒 <b>Приватные каналы ({len(private_channels)}):</b>\n")
        for item in private_channels:
            chat_title = item.get('chat', '?')
            username = item.get('username', '')
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"• <a href='{link}'>{chat_title}</a>")
            else:
                text_lines.append(f"• {chat_title}")
        text_lines.append("")

    pending_approval = details.get('pending_approval', [])
    if pending_approval:
        text_lines.append(f"⏳ <b>Ожидают одобрения ({len(pending_approval)}):</b>\n")
        for item in pending_approval:
            chat_title = item.get('chat', '?')
            username = item.get('username', '')
            status = item.get('status', 'unknown')
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"📝 <a href='{link}'>{chat_title}</a>")
            else:
                text_lines.append(f"📝 {chat_title}")
        text_lines.append("")

    errors = details.get('errors', [])
    if errors:
        text_lines.append(f"\n❌ <b>Ошибки ({len(errors)}):</b>\n")
        for item in errors[:10]:
            chat_title = item.get('chat', '?')
            username = item.get('username', '')
            error_msg = item.get('error', 'Unknown')
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"• <a href='{link}'>{chat_title}</a>")
            else:
                text_lines.append(f"• <b>{chat_title}</b>")
            text_lines.append(f"  <i>{error_msg[:100]}</i>\n")
        if len(errors) > 10:
            text_lines.append(f"<i>...+{len(errors) - 10}</i>")

    flood_wait = details.get('flood_wait', [])
    if flood_wait:
        text_lines.append(f"\n⏳ <b>FloodWait ({len(flood_wait)}):</b>\n")
        for item in flood_wait[:5]:
            chat_title = item.get('chat', '?')
            username = item.get('username', '')
            wait_seconds = item.get('wait_seconds', 0)
            if username:
                link = f"https://t.me/{username}"
                text_lines.append(f"• <a href='{link}'>{chat_title}</a> ({wait_seconds}s)")
            else:
                text_lines.append(f"• {chat_title} ({wait_seconds}s)")

    joined_text = "\n".join(text_lines)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.back", lang), callback_data="menu:chats")

    await callback.message.edit_text(
        joined_text,
        reply_markup=builder.as_markup(),
        disable_web_page_preview=True
    )
    await callback.answer()


## Обработка отмены во время добавления чата
@router.message(Command("cancel"), AddChatStates())
async def cancel_add_chat(message: Message, state: FSMContext, lang: str = "ru"):
    """
    Отменяет процесс добавления чата.
    """
    await state.clear()
    await message.answer(
        t("common.cancel", lang),
        reply_markup=get_chats_menu_keyboard(lang)
    )
