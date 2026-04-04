"""
## Обработка ошибок базы данных
Декораторы и утилиты для graceful обработки ошибок БД.
"""

import logging
import asyncio
from typing import TypeVar, Callable, Any, Optional
from functools import wraps

from sqlalchemy.exc import (
    SQLAlchemyError,
    DBAPIError,
    DisconnectionError,
    OperationalError,
    IntegrityError,
    TimeoutError as SQLTimeoutError
)

from shared.utils.error_handler import get_error_handler, ErrorType, ErrorSeverity


logger = logging.getLogger(__name__)


T = TypeVar('T')


## Обработчик ошибок БД с автоматическим retry
def handle_db_errors(
    operation: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    notify_operator: bool = True
):
    """
    Декоратор для обработки ошибок БД с автоматическими повторными попытками.
    
    Args:
        operation: Описание операции для логирования
        max_retries: Максимальное количество повторных попыток
        retry_delay: Задержка между попытками (секунды)
        notify_operator: Отправлять уведомление оператору при критических ошибках
        
    Example:
        @handle_db_errors("get_lead_by_id", max_retries=3)
        async def get_lead_by_id(session, lead_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            error_handler = get_error_handler()
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                    
                except DisconnectionError as e:
                    last_error = e
                    logger.warning(
                        f"⚠️ [{operation}] Потеряно соединение с БД (попытка {attempt + 1}/{max_retries}): {e}"
                    )
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    else:
                        ## Критическая ошибка - все попытки исчерпаны
                        await error_handler.handle_database_error(
                            error=e,
                            operation=operation,
                            notify=notify_operator
                        )
                        
                except OperationalError as e:
                    last_error = e
                    logger.warning(
                        f"⚠️ [{operation}] Операционная ошибка БД (попытка {attempt + 1}/{max_retries}): {e}"
                    )
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        await error_handler.handle_database_error(
                            error=e,
                            operation=operation,
                            notify=notify_operator
                        )
                        
                except SQLTimeoutError as e:
                    last_error = e
                    logger.warning(
                        f"⚠️ [{operation}] Таймаут БД (попытка {attempt + 1}/{max_retries}): {e}"
                    )
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        await error_handler.handle_database_error(
                            error=e,
                            operation=operation,
                            notify=False  # Таймауты обычно временные
                        )
                        
                except IntegrityError as e:
                    ## Ошибки целостности данных не retry'ятся
                    logger.error(f"❌ [{operation}] Ошибка целостности данных: {e}")
                    await error_handler.handle_database_error(
                        error=e,
                        operation=operation,
                        notify=False  # Это ошибка приложения, а не инфраструктуры
                    )
                    raise
                    
                except DBAPIError as e:
                    last_error = e
                    logger.error(f"❌ [{operation}] Ошибка DBAPI: {e}")
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        await error_handler.handle_database_error(
                            error=e,
                            operation=operation,
                            notify=notify_operator
                        )
                        
                except SQLAlchemyError as e:
                    ## Общие ошибки SQLAlchemy
                    logger.error(f"❌ [{operation}] Ошибка SQLAlchemy: {e}")
                    await error_handler.handle_database_error(
                        error=e,
                        operation=operation,
                        notify=notify_operator
                    )
                    raise
                    
                except Exception as e:
                    ## Неожиданные ошибки
                    logger.exception(f"💥 [{operation}] Непредвиденная ошибка: {e}")
                    await error_handler.handle_error(
                        error=e,
                        error_type=ErrorType.DATABASE,
                        severity=ErrorSeverity.HIGH,
                        context={"operation": operation},
                        notify_operator=notify_operator
                    )
                    raise
            
            # Если мы здесь, значит все попытки исчерпаны
            logger.critical(
                f"🔥 [{operation}] Все {max_retries} попыток исчерпаны. Последняя ошибка: {last_error}"
            )
            raise last_error
        
        return wrapper
    
    return decorator


## Простой декоратор для логирования ошибок БД без retry
def log_db_errors(operation: str):
    """
    Простой декоратор для логирования ошибок БД без автоматических повторных попыток.
    
    Args:
        operation: Описание операции
        
    Example:
        @log_db_errors("delete_account")
        async def delete_account(session, account_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except SQLAlchemyError as e:
                logger.error(f"❌ [{operation}] Ошибка БД: {type(e).__name__}: {e}")
                raise
            except Exception as e:
                logger.exception(f"💥 [{operation}] Непредвиденная ошибка: {e}")
                raise
        
        return wrapper
    
    return decorator


## Проверка доступности БД
async def check_database_health() -> tuple[bool, Optional[str]]:
    """
    Проверка доступности и работоспособности БД.
    
    Returns:
        Tuple (is_healthy, error_message)
    """
    try:
        from shared.database.engine import get_session
        from sqlalchemy import text
        
        async with get_session() as session:
            # Простой SELECT запрос для проверки соединения
            result = await session.execute(text("SELECT 1"))
            result.scalar()
            
        logger.info("✅ База данных доступна и работает")
        return True, None
        
    except DisconnectionError as e:
        error_msg = f"Потеряно соединение с БД: {e}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg
        
    except OperationalError as e:
        error_msg = f"БД недоступна: {e}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Непредвиденная ошибка при проверке БД: {e}"
        logger.exception(f"💥 {error_msg}")
        return False, error_msg


## Контекстный менеджер для безопасных транзакций
class SafeTransaction:
    """
    Контекстный менеджер для безопасной работы с транзакциями БД.
    Автоматически откатывает изменения при ошибках.
    
    Example:
        async with SafeTransaction("create_lead") as session:
            lead = await create_lead(session, ...)
            await session.commit()
    """
    
    def __init__(self, operation: str):
        self.operation = operation
        self.session = None
        
    async def __aenter__(self):
        from shared.database.engine import get_session
        
        self.session = get_session()
        session = await self.session.__aenter__()
        logger.debug(f"🔓 [{self.operation}] Транзакция началась")
        return session
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(
                f"❌ [{self.operation}] Ошибка в транзакции: {exc_type.__name__}: {exc_val}"
            )
            
            # Обрабатываем ошибку через error_handler
            if issubclass(exc_type, SQLAlchemyError):
                error_handler = get_error_handler()
                await error_handler.handle_database_error(
                    error=exc_val,
                    operation=self.operation,
                    notify=False
                )
        else:
            logger.debug(f"✅ [{self.operation}] Транзакция успешно завершена")
        
        # Закрываем сессию
        return await self.session.__aexit__(exc_type, exc_val, exc_tb)


if __name__ == "__main__":
    # Тестирование
    import asyncio
    
    @handle_db_errors("test_operation", max_retries=3)
    async def test_db_operation():
        # Имитация ошибки БД
        from sqlalchemy.exc import OperationalError
        raise OperationalError("Test error", None, None)
    
    async def test():
        try:
            await test_db_operation()
        except Exception as e:
            print(f"Поймано исключение: {e}")
        
        # Проверка здоровья БД
        is_healthy, error = await check_database_health()
        print(f"БД здорова: {is_healthy}, Ошибка: {error}")
    
    # asyncio.run(test())
    print("✅ Модуль database error_handling готов к использованию")

