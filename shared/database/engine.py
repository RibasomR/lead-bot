"""
## Database Engine и Session Management
Асинхронный движок PostgreSQL с пулом соединений.
"""

from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy import text

from config import settings
from shared.database.models import Base


## Глобальные переменные для движка и фабрики сессий
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


## Создание асинхронного движка БД
def get_engine() -> AsyncEngine:
    """
    Возвращает или создаёт асинхронный движок SQLAlchemy.
    Используется пул соединений для оптимизации производительности.
    """
    global _engine
    
    if _engine is None:
        _engine = create_async_engine(
            str(settings.database_url),
            echo=settings.log_level == "DEBUG",  # SQL логи только в DEBUG режиме
            pool_size=30,  # Увеличен размер пула для большого количества задач
            max_overflow=50,  # Увеличен overflow для пиковых нагрузок
            pool_pre_ping=True,  # Проверка соединений перед использованием
            pool_recycle=3600,  # Переподключение каждый час
            pool_timeout=60,  # Увеличен таймаут ожидания соединения до 60 сек
        )
    
    return _engine


## Фабрика асинхронных сессий
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Возвращает фабрику для создания асинхронных сессий БД.
    """
    global _async_session_factory
    
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Не сбрасывать объекты после коммита
            autoflush=False,  # Ручной контроль flush
            autocommit=False  # Ручной контроль коммитов
        )
    
    return _async_session_factory


## Контекстный менеджер для работы с сессией
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Контекстный менеджер для получения сессии БД.
    
    Пример использования:
        async with get_session() as session:
            result = await session.execute(select(Account))
            accounts = result.scalars().all()
    """
    session_factory = get_session_factory()
    session = session_factory()
    
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


## Инициализация всех таблиц
async def init_db() -> None:
    """
    Создаёт все таблицы в БД, если они не существуют.
    ВНИМАНИЕ: Для продакшена используйте миграции Alembic!
    """
    engine = get_engine()
    
    async with engine.begin() as conn:
        # Создаём все таблицы
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ База данных инициализирована")


## Удаление всех таблиц (только для разработки!)
async def drop_db() -> None:
    """
    ОПАСНО! Удаляет все таблицы из БД.
    Использовать только для разработки и тестирования!
    """
    engine = get_engine()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("⚠️ Все таблицы удалены")


## Проверка подключения к БД
async def check_connection() -> bool:
    """
    Проверяет соединение с БД.
    Возвращает True, если соединение успешно.
    """
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False


## Закрытие всех соединений
async def dispose_engine() -> None:
    """
    Закрывает все соединения с БД и освобождает ресурсы.
    Вызывать при завершении работы приложения.
    """
    global _engine, _async_session_factory
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        print("✅ Соединения с БД закрыты")


## Получение информации о пуле соединений
async def get_pool_status() -> dict:
    """
    Возвращает статистику пула соединений.
    Полезно для мониторинга и отладки.
    """
    engine = get_engine()
    pool = engine.pool
    
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow()
    }


if __name__ == "__main__":
    import asyncio
    
    async def test_connection():
        """Тестирование подключения к БД"""
        print("🔍 Проверка подключения к БД...")
        
        if await check_connection():
            print("✅ Подключение успешно")
            
            # Показываем статус пула
            status = await get_pool_status()
            print(f"📊 Статус пула соединений: {status}")
        else:
            print("❌ Не удалось подключиться к БД")
        
        await dispose_engine()
    
    asyncio.run(test_connection())

