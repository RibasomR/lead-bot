"""
## FSM States для Admin Bot
Состояния для работы с конечным автоматом (Finite State Machine).
"""

from aiogram.fsm.state import State, StatesGroup


## Состояния добавления чата
class AddChatStates(StatesGroup):
    """Состояния процесса добавления чата в мониторинг"""
    waiting_for_chat_forward = State()  # Ожидание пересылки сообщения из чата
    waiting_for_chat_link = State()  # Ожидание ссылки на чат
    waiting_for_priority = State()  # Ожидание приоритета


## Состояния добавления аккаунта
class AddAccountStates(StatesGroup):
    """Состояния процесса добавления аккаунта"""
    waiting_for_phone = State()  # Ожидание номера телефона
    waiting_for_label = State()  # Ожидание названия аккаунта
    waiting_for_role = State()   # Ожидание выбора роли (monitor/reply)


## Состояния авторизации аккаунта
class AuthAccountStates(StatesGroup):
    """Состояния процесса авторизации аккаунта"""
    waiting_for_code = State()  # Ожидание кода авторизации
    waiting_for_password = State()  # Ожидание 2FA пароля


## Состояния работы с лидом
class LeadStates(StatesGroup):
    """Состояния работы с лидом"""
    viewing_lead = State()  # Просмотр лида
    waiting_for_custom_text = State()  # Ожидание ввода своего текста ответа
    selecting_account = State()  # Выбор аккаунта для отправки
    selecting_style = State()  # Выбор стиля ответа


## Состояния редактирования черновика (v2)
class EditDraftStates(StatesGroup):
    """Состояния редактирования черновика ответа"""
    waiting_for_edited_text = State()  # Ожидание отредактированного текста


## Состояния перегенерации черновика с комментарием
class RegenerateDraftStates(StatesGroup):
    """Состояния перегенерации черновика с фидбеком оператора"""
    waiting_for_feedback = State()  # Ожидание комментария оператора


## Состояния редактирования профиля (v2)
class ProfileStates(StatesGroup):
    """Состояния редактирования профиля фрилансера"""
    editing_stack = State()       # Редактирование стека технологий
    editing_specialization = State()  # Редактирование специализации
    editing_about = State()       # Редактирование "о себе"
    editing_min_budget = State()  # Редактирование минимального бюджета
    editing_portfolio = State()   # Редактирование ссылки на портфолио


## Состояния настроек
class SettingsStates(StatesGroup):
    """Состояния изменения настроек"""
    editing_keywords = State()  # Редактирование ключевых слов
    editing_limits = State()  # Редактирование лимитов

