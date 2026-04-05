"""
## Клавиатуры для Admin Bot
Генераторы клавиатур для различных меню и действий.
Все текстовые строки получаются через t() для мультиязычности.
"""

from typing import List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.database.models import Account, Chat, CommunicationStyle
from shared.locales import t


## Клавиатура выбора языка
def get_language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("lang.btn_ru"), callback_data="lang:set:ru")
    builder.button(text=t("lang.btn_en"), callback_data="lang:set:en")
    builder.adjust(1)
    return builder.as_markup()


## Главное меню бота
def get_main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=t("menu.leads", lang), callback_data="menu:leads")
    builder.button(text=t("menu.stats", lang), callback_data="menu:stats")
    builder.button(text=t("menu.chats", lang), callback_data="menu:chats")
    builder.button(text=t("menu.accounts", lang), callback_data="menu:accounts")
    builder.button(text=t("menu.profile", lang), callback_data="menu:profile")
    builder.button(text=t("menu.search", lang), callback_data="menu:search")
    builder.button(text=t("menu.language", lang), callback_data="menu:language")

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


## Меню управления чатами
def get_chats_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=t("chats.btn_my_chats", lang), callback_data="chats:list")
    builder.button(text=t("chats.btn_add", lang), callback_data="chats:add")
    builder.button(text=t("chats.btn_blacklist", lang), callback_data="chats:blacklist")
    builder.button(text=t("chats.btn_discovery", lang), callback_data="channels:discovery")
    builder.button(text=t("chats.btn_join_all", lang), callback_data="chats:join_all")
    builder.button(text=t("menu.back", lang), callback_data="menu:main")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


## Меню управления аккаунтами
def get_accounts_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=t("accounts.btn_list", lang), callback_data="accounts:list")
    builder.button(text=t("accounts.btn_add", lang), callback_data="accounts:add")
    builder.button(text=t("menu.back", lang), callback_data="menu:main")

    builder.adjust(2, 1)
    return builder.as_markup()


## Клавиатура для управления конкретным чатом
def get_chat_actions_keyboard(chat_id: int, enabled: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if enabled:
        builder.button(text=t("chats.btn_disable", lang), callback_data=f"chat:disable:{chat_id}")
    else:
        builder.button(text=t("chats.btn_enable", lang), callback_data=f"chat:enable:{chat_id}")

    builder.button(text=t("chats.btn_whitelist", lang), callback_data=f"chat:whitelist:{chat_id}")
    builder.button(text=t("chats.btn_to_blacklist", lang), callback_data=f"chat:blacklist:{chat_id}")
    builder.button(text=t("chats.btn_delete", lang), callback_data=f"chat:delete:{chat_id}")
    builder.button(text=t("menu.back_to_list", lang), callback_data="chats:list")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


## Клавиатура выбора стиля для аккаунта
def get_style_selection_keyboard(account_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text=t("accounts.style_polite", lang),
        callback_data=f"account:style:{account_id}:{CommunicationStyle.POLITE.value}"
    )
    builder.button(
        text=t("accounts.style_friendly", lang),
        callback_data=f"account:style:{account_id}:{CommunicationStyle.FRIENDLY.value}"
    )
    builder.button(
        text=t("accounts.style_aggressive", lang),
        callback_data=f"account:style:{account_id}:{CommunicationStyle.AGGRESSIVE.value}"
    )
    builder.button(text=t("menu.back", lang), callback_data="accounts:list")

    builder.adjust(1)
    return builder.as_markup()


## Клавиатура для управления аккаунтом
def get_account_actions_keyboard(
    account_id: int,
    enabled: bool,
    is_authorized: bool = False,
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if not is_authorized:
        builder.button(text=t("accounts.btn_auth", lang), callback_data=f"account:auth:{account_id}")

    if enabled:
        builder.button(text=t("accounts.btn_disable", lang), callback_data=f"account:disable:{account_id}")
    else:
        builder.button(text=t("accounts.btn_enable", lang), callback_data=f"account:enable:{account_id}")

    builder.button(text=t("accounts.btn_style", lang), callback_data=f"account:change_style:{account_id}")
    builder.button(text=t("accounts.btn_delete", lang), callback_data=f"account:delete:{account_id}")
    builder.button(text=t("menu.back_to_list", lang), callback_data="accounts:list")

    builder.adjust(2, 2, 1)
    return builder.as_markup()


## Пагинация для списков
def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if current_page > 0:
        builder.button(text=t("common.prev", lang), callback_data=f"{callback_prefix}:{current_page - 1}")

    builder.button(
        text=t("common.page_indicator", lang, current=current_page + 1, total=total_pages),
        callback_data="pagination:current"
    )

    if current_page < total_pages - 1:
        builder.button(text=t("common.next", lang), callback_data=f"{callback_prefix}:{current_page + 1}")

    builder.adjust(3)
    return builder.as_markup()


## Подтверждение действия
def get_confirmation_keyboard(
    action: str,
    entity_id: int,
    entity_type: str,
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text=t("common.confirm_yes", lang),
        callback_data=f"{entity_type}:{action}_confirm:{entity_id}"
    )
    builder.button(
        text=t("common.confirm_no", lang),
        callback_data=f"{entity_type}:cancel:{entity_id}"
    )

    builder.adjust(1)
    return builder.as_markup()


## ========== Клавиатуры для автопоиска каналов ==========

def get_channel_discovery_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=t("discovery.btn_start", lang), callback_data="channels:start_search")
    builder.button(text=t("discovery.btn_view", lang), callback_data="channels:view_recommendations")
    builder.button(text=t("discovery.btn_add_top", lang), callback_data="channels:add_top")
    builder.button(text=t("menu.back", lang), callback_data="channels:back")

    builder.adjust(2, 1, 1)
    return builder.as_markup()


def get_channel_candidate_keyboard(
    candidate_id: int,
    index: int,
    total: int,
    ai_score: float,
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=t("discovery.btn_add_monitoring", lang), callback_data=f"candidate:add:{candidate_id}")
    builder.button(text=t("discovery.btn_ignore", lang), callback_data=f"candidate:ignore:{candidate_id}")

    if total > 1:
        builder.button(text=t("discovery.btn_prev", lang), callback_data="candidate:nav:prev")
        builder.button(text=f"{index + 1}/{total}", callback_data="noop")
        builder.button(text=t("discovery.btn_next", lang), callback_data="candidate:nav:next")

    builder.button(text=t("discovery.btn_menu", lang), callback_data="channels:discovery")

    if total > 1:
        builder.adjust(2, 3, 1)
    else:
        builder.adjust(2, 1)

    return builder.as_markup()


def get_candidates_list_keyboard(
    candidates_ids: List[int],
    page: int = 0,
    per_page: int = 10,
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(candidates_ids))

    for i in range(start_idx, end_idx):
        builder.button(
            text=t("common.channel_n", lang, n=i + 1),
            callback_data=f"candidate:view:{candidates_ids[i]}"
        )

    builder.adjust(2)

    total_pages = (len(candidates_ids) + per_page - 1) // per_page
    nav_builder = InlineKeyboardBuilder()

    if page > 0:
        nav_builder.button(text=t("common.prev", lang), callback_data=f"candidates:page:{page - 1}")

    nav_builder.button(
        text=t("common.page_indicator", lang, current=page + 1, total=total_pages),
        callback_data="noop"
    )

    if page < total_pages - 1:
        nav_builder.button(text=t("common.forward", lang), callback_data=f"candidates:page:{page + 1}")

    nav_builder.adjust(3)

    back_builder = InlineKeyboardBuilder()
    back_builder.button(text=t("discovery.btn_menu", lang), callback_data="channels:discovery")

    builder.attach(nav_builder)
    builder.attach(back_builder)

    return builder.as_markup()
