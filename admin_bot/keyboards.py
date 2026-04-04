"""
## Клавиатуры для Admin Bot
Генераторы клавиатур для различных меню и действий.
"""

from typing import List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.database.models import Account, Chat, CommunicationStyle


## Главное меню бота
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт главное меню бота с основными разделами.
    
    Returns:
        InlineKeyboardMarkup с кнопками главного меню
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📬 Лиды", callback_data="menu:leads")
    builder.button(text="📊 Статистика", callback_data="menu:stats")
    builder.button(text="💬 Чаты", callback_data="menu:chats")
    builder.button(text="👤 Аккаунты", callback_data="menu:accounts")
    builder.button(text="🧑‍💻 Профиль", callback_data="menu:profile")
    builder.button(text="🔍 Поиск", callback_data="menu:search")

    builder.adjust(2, 2, 2)
    return builder.as_markup()


## Меню управления чатами
def get_chats_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт меню управления чатами.
    
    Returns:
        InlineKeyboardMarkup с кнопками управления чатами
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📋 Мои чаты", callback_data="chats:list")
    builder.button(text="➕ Добавить", callback_data="chats:add")
    builder.button(text="🚫 Чёрный список", callback_data="chats:blacklist")
    builder.button(text="🔎 Автопоиск", callback_data="channels:discovery")
    builder.button(text="📡 Подписать монитор", callback_data="chats:join_all")
    builder.button(text="🔙 Назад", callback_data="menu:main")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


## Меню управления аккаунтами
def get_accounts_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создаёт меню управления аккаунтами.
    
    Returns:
        InlineKeyboardMarkup с кнопками управления аккаунтами
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📋 Список аккаунтов", callback_data="accounts:list")
    builder.button(text="➕ Добавить аккаунт", callback_data="accounts:add")
    builder.button(text="🔙 Назад", callback_data="menu:main")
    
    builder.adjust(2, 1)
    return builder.as_markup()


## Клавиатура для управления конкретным чатом
def get_chat_actions_keyboard(chat_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с действиями для конкретного чата.
    
    Args:
        chat_id: ID чата в базе данных
        enabled: Включён ли мониторинг чата
        
    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка включения/выключения
    if enabled:
        builder.button(text="🔴 Выключить", callback_data=f"chat:disable:{chat_id}")
    else:
        builder.button(text="🟢 Включить", callback_data=f"chat:enable:{chat_id}")
    
    builder.button(text="⚪ В белый список", callback_data=f"chat:whitelist:{chat_id}")
    builder.button(text="⚫ В чёрный список", callback_data=f"chat:blacklist:{chat_id}")
    builder.button(text="🗑 Удалить", callback_data=f"chat:delete:{chat_id}")
    builder.button(text="🔙 К списку", callback_data="chats:list")
    
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


## Клавиатура выбора стиля для аккаунта
def get_style_selection_keyboard(account_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора стиля общения аккаунта.
    
    Args:
        account_id: ID аккаунта в базе данных
        
    Returns:
        InlineKeyboardMarkup с кнопками выбора стиля
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🎩 Вежливый/Деловой",
        callback_data=f"account:style:{account_id}:{CommunicationStyle.POLITE.value}"
    )
    builder.button(
        text="😊 Дружеский",
        callback_data=f"account:style:{account_id}:{CommunicationStyle.FRIENDLY.value}"
    )
    builder.button(
        text="💪 Агрессивный/Жёсткий",
        callback_data=f"account:style:{account_id}:{CommunicationStyle.AGGRESSIVE.value}"
    )
    builder.button(text="🔙 Назад", callback_data="accounts:list")
    
    builder.adjust(1)
    return builder.as_markup()


## Клавиатура для управления аккаунтом
def get_account_actions_keyboard(
    account_id: int,
    enabled: bool,
    is_authorized: bool = False
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с действиями для конкретного аккаунта.
    
    Args:
        account_id: ID аккаунта в базе данных
        enabled: Активен ли аккаунт
        is_authorized: Авторизован ли аккаунт (tg_user_id != 0)
        
    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка авторизации (только для неавторизованных)
    if not is_authorized:
        builder.button(text="🔐 Авторизовать", callback_data=f"account:auth:{account_id}")
    
    # Кнопка включения/выключения
    if enabled:
        builder.button(text="🔴 Деактивировать", callback_data=f"account:disable:{account_id}")
    else:
        builder.button(text="🟢 Активировать", callback_data=f"account:enable:{account_id}")
    
    builder.button(text="🎨 Изменить стиль", callback_data=f"account:change_style:{account_id}")
    builder.button(text="🗑 Удалить", callback_data=f"account:delete:{account_id}")
    builder.button(text="🔙 К списку", callback_data="accounts:list")
    
    builder.adjust(2, 2, 1)
    return builder.as_markup()


## Пагинация для списков
def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру пагинации для списков.
    
    Args:
        current_page: Текущая страница (с 0)
        total_pages: Общее количество страниц
        callback_prefix: Префикс для callback_data (например, "leads:page" или "chats:page")
        
    Returns:
        InlineKeyboardMarkup с кнопками пагинации
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Назад"
    if current_page > 0:
        builder.button(text="◀️ Назад", callback_data=f"{callback_prefix}:{current_page - 1}")
    
    # Индикатор страницы
    builder.button(
        text=f"📄 {current_page + 1}/{total_pages}",
        callback_data="pagination:current"
    )
    
    # Кнопка "Вперёд"
    if current_page < total_pages - 1:
        builder.button(text="▶️ Вперёд", callback_data=f"{callback_prefix}:{current_page + 1}")
    
    builder.adjust(3)
    return builder.as_markup()


## Подтверждение действия
def get_confirmation_keyboard(
    action: str,
    entity_id: int,
    entity_type: str
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру подтверждения действия.
    
    Args:
        action: Действие (delete, disable, etc.)
        entity_id: ID сущности
        entity_type: Тип сущности (chat, account, lead)
        
    Returns:
        InlineKeyboardMarkup с кнопками подтверждения
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="✅ Да, подтвердить",
        callback_data=f"{entity_type}:{action}_confirm:{entity_id}"
    )
    builder.button(
        text="❌ Нет, отменить",
        callback_data=f"{entity_type}:cancel:{entity_id}"
    )
    
    builder.adjust(1)
    return builder.as_markup()


## ========== Клавиатуры для автопоиска каналов (Фаза 7.3) ==========

def get_channel_discovery_menu_keyboard() -> InlineKeyboardMarkup:
    """
    ## Меню автопоиска каналов
    
    Returns:
        InlineKeyboardMarkup с кнопками меню автопоиска
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="🚀 Запустить поиск", callback_data="channels:start_search")
    builder.button(text="⭐ Посмотреть рекомендации", callback_data="channels:view_recommendations")
    builder.button(text="➕ Добавить лучшие", callback_data="channels:add_top")
    builder.button(text="🔙 Назад", callback_data="channels:back")
    
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def get_channel_candidate_keyboard(
    candidate_id: int,
    index: int,
    total: int,
    ai_score: float
) -> InlineKeyboardMarkup:
    """
    ## Клавиатура для карточки кандидата канала
    
    Args:
        candidate_id: ID кандидата в БД
        index: Текущий индекс в списке
        total: Общее количество кандидатов
        ai_score: AI-оценка канала
        
    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    builder = InlineKeyboardBuilder()
    
    # Основные действия
    builder.button(text="✅ Добавить в мониторинг", callback_data=f"candidate:add:{candidate_id}")
    builder.button(text="🚫 Игнорировать", callback_data=f"candidate:ignore:{candidate_id}")
    
    # Навигация
    if total > 1:
        builder.button(text="◀️ Предыдущий", callback_data="candidate:nav:prev")
        builder.button(text=f"{index + 1}/{total}", callback_data="noop")
        builder.button(text="▶️ Следующий", callback_data="candidate:nav:next")
    
    # Возврат
    builder.button(text="🔙 К меню", callback_data="channels:discovery")
    
    if total > 1:
        builder.adjust(2, 3, 1)
    else:
        builder.adjust(2, 1)
    
    return builder.as_markup()


def get_candidates_list_keyboard(
    candidates_ids: List[int],
    page: int = 0,
    per_page: int = 10
) -> InlineKeyboardMarkup:
    """
    ## Клавиатура списка кандидатов с пагинацией
    
    Args:
        candidates_ids: Список ID кандидатов
        page: Текущая страница
        per_page: Количество на странице
        
    Returns:
        InlineKeyboardMarkup со списком и навигацией
    """
    builder = InlineKeyboardBuilder()
    
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(candidates_ids))
    
    # Кнопки с кандидатами
    for i in range(start_idx, end_idx):
        builder.button(
            text=f"📺 Канал {i + 1}",
            callback_data=f"candidate:view:{candidates_ids[i]}"
        )
    
    builder.adjust(2)
    
    # Пагинация
    total_pages = (len(candidates_ids) + per_page - 1) // per_page
    nav_builder = InlineKeyboardBuilder()
    
    if page > 0:
        nav_builder.button(text="◀️ Назад", callback_data=f"candidates:page:{page - 1}")
    
    nav_builder.button(text=f"📄 {page + 1}/{total_pages}", callback_data="noop")
    
    if page < total_pages - 1:
        nav_builder.button(text="Вперёд ▶️", callback_data=f"candidates:page:{page + 1}")
    
    nav_builder.adjust(3)
    
    # Возврат
    back_builder = InlineKeyboardBuilder()
    back_builder.button(text="🔙 К меню", callback_data="channels:discovery")
    
    # Объединяем
    builder.attach(nav_builder)
    builder.attach(back_builder)
    
    return builder.as_markup()

