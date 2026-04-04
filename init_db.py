"""
## Скрипт инициализации базы данных
Применяет миграции и проверяет работоспособность БД.
"""

import asyncio
import sys

from config import validate_config
from shared.database.engine import check_connection, get_pool_status
from shared.database.migrations import run_migrations, get_current_revision


async def main():
    """Главная функция инициализации БД"""
    
    print("=" * 60)
    print("🚀 LeadHunter - Инициализация базы данных")
    print("=" * 60)
    print()
    
    # 1. Валидация конфигурации
    try:
        print("🔍 Проверка конфигурации...")
        validate_config()
        print()
    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        print("💡 Проверьте файл .env и убедитесь, что все переменные заданы")
        sys.exit(1)
    
    # 2. Проверка подключения к БД
    try:
        print("🔍 Проверка подключения к PostgreSQL...")
        if not await check_connection():
            print("❌ Не удалось подключиться к базе данных")
            print("💡 Убедитесь, что PostgreSQL запущен и настройки подключения верны")
            sys.exit(1)
        print("✅ Подключение к БД установлено")
        print()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        sys.exit(1)
    
    # 3. Получение текущей версии БД
    try:
        print("📊 Проверка текущей версии схемы БД...")
        current_rev = await get_current_revision()
        print(f"   Текущая версия: {current_rev}")
        print()
    except Exception as e:
        print(f"⚠️  Не удалось получить версию БД: {e}")
        print()
    
    # 4. Применение миграций
    try:
        await run_migrations()
        print()
    except Exception as e:
        print(f"❌ Ошибка при применении миграций: {e}")
        sys.exit(1)
    
    # 5. Проверка новой версии
    try:
        new_rev = await get_current_revision()
        print(f"📊 Новая версия схемы БД: {new_rev}")
        print()
    except Exception as e:
        print(f"⚠️  Не удалось получить версию БД: {e}")
        print()
    
    # 6. Статус пула соединений
    try:
        print("📊 Статус пула соединений:")
        pool_status = await get_pool_status()
        print(f"   Размер пула: {pool_status['size']}")
        print(f"   Активных соединений: {pool_status['checked_out']}")
        print(f"   Свободных соединений: {pool_status['checked_in']}")
        print(f"   Overflow: {pool_status['overflow']}")
        print(f"   Всего: {pool_status['total']}")
        print()
    except Exception as e:
        print(f"⚠️  Не удалось получить статус пула: {e}")
        print()
    
    print("=" * 60)
    print("✅ Инициализация завершена успешно!")
    print("=" * 60)
    print()
    print("💡 Следующие шаги:")
    print("   1. Запустите Admin Bot: python -m admin_bot.main")
    print("   2. Запустите Lead Listener: python -m lead_listener.main")
    print("   3. Или запустите всё через Docker: docker-compose up -d")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Инициализация прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)

