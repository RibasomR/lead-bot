"""
## Database Package
Модуль для работы с базой данных PostgreSQL.
"""

# Экспортируем модели
from shared.database.models import (
    Base,
    Account,
    Chat,
    Lead,
    LeadAIData,
    Reply,
    LeadStatus,
    ChatType,
    CommunicationStyle
)

# Экспортируем функции для работы с движком
from shared.database.engine import (
    get_engine,
    get_session_factory,
    get_session,
    init_db,
    drop_db,
    check_connection,
    dispose_engine,
    get_pool_status
)

# Экспортируем CRUD операции
from shared.database import crud

__all__ = [
    # Models
    "Base",
    "Account",
    "Chat",
    "Lead",
    "LeadAIData",
    "Reply",
    "LeadStatus",
    "ChatType",
    "CommunicationStyle",
    
    # Engine functions
    "get_engine",
    "get_session_factory",
    "get_session",
    "init_db",
    "drop_db",
    "check_connection",
    "dispose_engine",
    "get_pool_status",
    
    # CRUD module
    "crud",
]
