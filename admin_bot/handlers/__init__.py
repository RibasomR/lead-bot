"""
## Модуль хендлеров Admin Bot
Обработчики команд и callback-запросов.
"""

from aiogram import Router

from . import start, chats, accounts, leads, channel_discovery, profile, search


## Создание главного роутера для всех хендлеров
def setup_handlers() -> Router:
    """
    Настраивает и возвращает главный роутер со всеми хендлерами.
    
    Returns:
        Router с подключёнными хендлерами
    """
    router = Router(name="main_router")
    
    ## Подключаем роутеры модулей
    ## ВАЖНО: Порядок имеет значение!
    ## Специфичные обработчики (с FSM состояниями) должны быть выше общих
    ## channel_discovery.router — deprecated в v2, заменяется search.router
    router.include_router(accounts.router)  # FSM состояния для аккаунтов
    router.include_router(chats.router)     # FSM состояния для чатов
    router.include_router(leads.router)     # FSM состояния для лидов
    router.include_router(profile.router)   # Профиль фрилансера (v2)
    router.include_router(search.router)    # Глобальный поиск (v2)
    router.include_router(start.router)     # Общие команды и fallback обработчики
    
    return router

