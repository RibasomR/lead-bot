"""
## Утилиты для работы с миграциями Alembic
Асинхронное применение миграций при старте приложения.
"""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from shared.database.engine import check_connection


## Получение конфигурации Alembic
def get_alembic_config() -> Config:
    """
    Создаёт конфигурацию Alembic.
    """
    # Путь к alembic.ini относительно корня проекта
    alembic_cfg = Config("alembic.ini")
    
    # Путь к папке с миграциями
    alembic_cfg.set_main_option("script_location", "migrations")
    
    return alembic_cfg


## Применение всех миграций
async def run_migrations() -> None:
    """
    Применяет все доступные миграции к базе данных.
    Запускается асинхронно через asyncio.
    """
    print("🔄 Проверка подключения к БД...")
    
    # Проверяем соединение
    if not await check_connection():
        raise ConnectionError("Не удалось подключиться к базе данных")
    
    print("✅ Подключение к БД успешно")
    print("🔄 Применение миграций...")
    
    try:
        # Получаем конфиг
        alembic_cfg = get_alembic_config()
        
        # Применяем миграции (синхронная операция)
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        
        print("✅ Миграции успешно применены")
        
    except Exception as e:
        print(f"❌ Ошибка при применении миграций: {e}")
        raise


## Откат последней миграции
async def rollback_migration(steps: int = 1) -> None:
    """
    Откатывает последние N миграций.
    
    Args:
        steps: Количество миграций для отката (по умолчанию 1)
    """
    print(f"🔄 Откат последних {steps} миграций...")
    
    try:
        alembic_cfg = get_alembic_config()
        
        # Откатываем миграции
        await asyncio.to_thread(command.downgrade, alembic_cfg, f"-{steps}")
        
        print(f"✅ Откат {steps} миграций выполнен")
        
    except Exception as e:
        print(f"❌ Ошибка при откате миграций: {e}")
        raise


## Создание новой миграции
def create_migration(message: str, autogenerate: bool = True) -> None:
    """
    Создаёт новую миграцию.
    
    Args:
        message: Описание миграции
        autogenerate: Автоматически определить изменения в моделях
    """
    print(f"🔄 Создание миграции: {message}")
    
    try:
        alembic_cfg = get_alembic_config()
        
        if autogenerate:
            command.revision(alembic_cfg, message=message, autogenerate=True)
        else:
            command.revision(alembic_cfg, message=message)
        
        print("✅ Миграция создана")
        
    except Exception as e:
        print(f"❌ Ошибка при создании миграции: {e}")
        raise


## Просмотр текущей версии БД
async def get_current_revision() -> str:
    """
    Возвращает текущую версию БД (revision).
    """
    try:
        alembic_cfg = get_alembic_config()
        
        # Получаем текущую версию
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        from config import settings
        
        # Создаём синхронный движок для Alembic
        sync_url = str(settings.database_url).replace('+asyncpg', '+psycopg2')
        engine = create_engine(sync_url)
        
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
        
        engine.dispose()
        
        return current_rev or "No migrations applied"
        
    except Exception as e:
        print(f"❌ Ошибка при получении версии БД: {e}")
        return "Error"


## Просмотр истории миграций
def show_migration_history() -> None:
    """
    Показывает историю миграций.
    """
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg, verbose=True)
        
    except Exception as e:
        print(f"❌ Ошибка при получении истории: {e}")
        raise


if __name__ == "__main__":
    import sys
    
    async def main():
        """CLI для работы с миграциями"""
        if len(sys.argv) < 2:
            print("""
Использование:
    python -m shared.database.migrations upgrade    - Применить все миграции
    python -m shared.database.migrations downgrade  - Откатить последнюю миграцию
    python -m shared.database.migrations create "message" - Создать новую миграцию
    python -m shared.database.migrations current    - Показать текущую версию
    python -m shared.database.migrations history    - Показать историю
            """)
            return
        
        command_name = sys.argv[1]
        
        if command_name == "upgrade":
            await run_migrations()
        
        elif command_name == "downgrade":
            steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            await rollback_migration(steps)
        
        elif command_name == "create":
            if len(sys.argv) < 3:
                print("❌ Укажите описание миграции")
                return
            message = sys.argv[2]
            create_migration(message)
        
        elif command_name == "current":
            revision = await get_current_revision()
            print(f"📊 Текущая версия БД: {revision}")
        
        elif command_name == "history":
            show_migration_history()
        
        else:
            print(f"❌ Неизвестная команда: {command_name}")
    
    asyncio.run(main())

