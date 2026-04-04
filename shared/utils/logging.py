"""
## Централизованная система логирования для всех сервисов
Унифицированная настройка логирования с поддержкой rotation и форматирования.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from config import settings


## Форматтер для красивого вывода логов
class ColoredFormatter(logging.Formatter):
    """
    Форматтер с цветными метками уровней логирования для консоли.
    """
    
    # Цветовые коды ANSI
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        # Добавляем цвет к уровню логирования
        if record.levelname in self.COLORS:
            record.levelname_colored = (
                f"{self.COLORS[record.levelname]}"
                f"{record.levelname:<8}"
                f"{self.RESET}"
            )
        else:
            record.levelname_colored = f"{record.levelname:<8}"
        
        return super().format(record)


## Настройка логирования для сервиса
def setup_logging(
    service_name: str,
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None,
    console: bool = True,
    file_logging: bool = True
) -> logging.Logger:
    """
    Настраивает систему логирования для конкретного сервиса.
    
    Args:
        service_name: Название сервиса (admin_bot, lead_listener, etc.)
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Путь к файлу логов (по умолчанию из settings)
        console: Выводить логи в консоль
        file_logging: Писать логи в файл
        
    Returns:
        Настроенный logger для сервиса
    """
    # Определяем уровень логирования
    if log_level is None:
        log_level = settings.log_level
    
    # Определяем файл логов
    if log_file is None:
        log_file = settings.logs_dir / f"{service_name}.log"
    
    # Создаём директорию для логов
    log_file.parent.mkdir(exist_ok=True, parents=True)
    
    # Получаем root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level))
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Формат для консоли (с цветами)
    console_format = (
        "%(asctime)s | %(levelname_colored)s | "
        "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    
    # Формат для файла (без цветов)
    file_format = (
        "%(asctime)s | %(levelname)-8s | "
        "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    
    # Консольный обработчик
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))
        
        console_formatter = ColoredFormatter(
            console_format,
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # Файловый обработчик с rotation
    if file_logging:
        # Rotating по размеру (10 MB)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, log_level))
        
        file_formatter = logging.Formatter(
            file_format,
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Настраиваем уровни для сторонних библиотек
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Возвращаем именованный logger для сервиса
    service_logger = logging.getLogger(service_name)
    service_logger.info(f"✅ Логирование настроено для {service_name}")
    service_logger.info(f"📁 Файл логов: {log_file}")
    service_logger.info(f"📊 Уровень логирования: {log_level}")
    
    return service_logger


## Декоратор для логирования исключений
def log_exceptions(logger: logging.Logger):
    """
    Декоратор для автоматического логирования исключений в функциях.
    
    Args:
        logger: Logger для записи исключений
        
    Example:
        @log_exceptions(logger)
        async def my_function():
            ...
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"❌ Исключение в {func.__name__}: {type(e).__name__}: {e}"
                )
                raise
        
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"❌ Исключение в {func.__name__}: {type(e).__name__}: {e}"
                )
                raise
        
        # Определяем, синхронная или асинхронная функция
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


## Класс для структурированного логирования
class StructuredLogger:
    """
    Обёртка над logging для структурированного логирования.
    Добавляет контекстную информацию к сообщениям.
    """
    
    def __init__(self, logger: logging.Logger, context: dict = None):
        self.logger = logger
        self.context = context or {}
    
    def _format_message(self, message: str) -> str:
        """Добавляет контекст к сообщению"""
        if self.context:
            context_str = " | ".join(f"{k}={v}" for k, v in self.context.items())
            return f"[{context_str}] {message}"
        return message
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(self._format_message(message), **kwargs)
    
    def info(self, message: str, **kwargs):
        self.logger.info(self._format_message(message), **kwargs)
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(self._format_message(message), **kwargs)
    
    def error(self, message: str, **kwargs):
        self.logger.error(self._format_message(message), **kwargs)
    
    def critical(self, message: str, **kwargs):
        self.logger.critical(self._format_message(message), **kwargs)
    
    def exception(self, message: str, **kwargs):
        self.logger.exception(self._format_message(message), **kwargs)
    
    def with_context(self, **context):
        """Создаёт новый logger с дополнительным контекстом"""
        new_context = {**self.context, **context}
        return StructuredLogger(self.logger, new_context)


if __name__ == "__main__":
    # Тестирование системы логирования
    logger = setup_logging("test_service")
    
    logger.debug("Debug сообщение")
    logger.info("Info сообщение")
    logger.warning("Warning сообщение")
    logger.error("Error сообщение")
    
    # Тест структурированного логирования
    structured = StructuredLogger(logger, {"user_id": 123, "action": "test"})
    structured.info("Тестовое сообщение со структурой")
    
    # Тест контекста
    user_logger = structured.with_context(session_id="abc123")
    user_logger.info("Сообщение с дополнительным контекстом")
    
    print("\n✅ Тестирование логирования завершено")

