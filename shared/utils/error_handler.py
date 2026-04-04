"""
## Централизованная обработка ошибок
Система обработки критических ошибок с уведомлениями оператору.
"""

import logging
import traceback
from typing import Optional, Callable, Any
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict

from aiogram import Bot

from config import settings


logger = logging.getLogger(__name__)


## Уровни критичности ошибок
class ErrorSeverity(str, Enum):
    """Уровни критичности ошибок"""
    LOW = "low"           # Некритичные ошибки, не требуют немедленного внимания
    MEDIUM = "medium"     # Важные ошибки, требуют внимания
    HIGH = "high"         # Критичные ошибки, требуют срочного внимания
    CRITICAL = "critical" # Катастрофические ошибки, система не работает


## Типы ошибок
class ErrorType(str, Enum):
    """Типы ошибок в системе"""
    DATABASE = "database"           # Ошибки БД
    API = "api"                     # Ошибки внешних API
    TELEGRAM = "telegram"           # Ошибки Telegram API
    AI = "ai"                       # Ошибки AI сервиса
    NETWORK = "network"             # Сетевые ошибки
    CONFIGURATION = "configuration" # Ошибки конфигурации
    INTERNAL = "internal"           # Внутренние ошибки


## Класс для обработки ошибок
class ErrorHandler:
    """
    Централизованный обработчик ошибок с уведомлениями оператору.
    """
    
    def __init__(self, bot: Optional[Bot] = None):
        self.bot = bot
        self.operator_id = settings.operator_user_id
        
        # Дедупликация уведомлений (не спамим одинаковыми ошибками)
        self._error_cooldown = defaultdict(lambda: None)
        self._cooldown_duration = timedelta(minutes=15)
        
        # Счетчики ошибок
        self._error_counts = defaultdict(int)
        
    def set_bot(self, bot: Bot):
        """Установить экземпляр бота для отправки уведомлений"""
        self.bot = bot
    
    async def handle_error(
        self,
        error: Exception,
        error_type: ErrorType,
        severity: ErrorSeverity,
        context: Optional[dict] = None,
        notify_operator: bool = True
    ) -> None:
        """
        Обработка ошибки с логированием и уведомлением оператору.
        
        Args:
            error: Исключение
            error_type: Тип ошибки
            severity: Уровень критичности
            context: Дополнительный контекст ошибки
            notify_operator: Отправлять ли уведомление оператору
        """
        # Формируем сообщение об ошибке
        error_msg = f"{type(error).__name__}: {str(error)}"
        
        # Логируем в зависимости от severity
        if severity == ErrorSeverity.CRITICAL:
            logger.critical(f"🔥 [{error_type.value.upper()}] {error_msg}", exc_info=error)
        elif severity == ErrorSeverity.HIGH:
            logger.error(f"❌ [{error_type.value.upper()}] {error_msg}", exc_info=error)
        elif severity == ErrorSeverity.MEDIUM:
            logger.warning(f"⚠️ [{error_type.value.upper()}] {error_msg}")
        else:
            logger.info(f"ℹ️ [{error_type.value.upper()}] {error_msg}")
        
        # Обновляем счетчик
        error_key = f"{error_type.value}:{type(error).__name__}"
        self._error_counts[error_key] += 1
        
        # Отправляем уведомление оператору
        if notify_operator and self._should_notify(error_key, severity):
            await self._notify_operator(error, error_type, severity, context)
    
    def _should_notify(self, error_key: str, severity: ErrorSeverity) -> bool:
        """
        Проверка, нужно ли отправлять уведомление (дедупликация).
        
        Args:
            error_key: Ключ ошибки
            severity: Уровень критичности
            
        Returns:
            True если нужно отправить уведомление
        """
        # Критичные ошибки всегда уведомляем
        if severity == ErrorSeverity.CRITICAL:
            return True
        
        # Проверяем cooldown
        last_notify = self._error_cooldown.get(error_key)
        
        if last_notify is None:
            self._error_cooldown[error_key] = datetime.utcnow()
            return True
        
        # Проверяем, прошло ли достаточно времени
        if datetime.utcnow() - last_notify > self._cooldown_duration:
            self._error_cooldown[error_key] = datetime.utcnow()
            return True
        
        return False
    
    async def _notify_operator(
        self,
        error: Exception,
        error_type: ErrorType,
        severity: ErrorSeverity,
        context: Optional[dict] = None
    ) -> None:
        """
        Отправка уведомления оператору о критической ошибке.
        
        Args:
            error: Исключение
            error_type: Тип ошибки
            severity: Уровень критичности
            context: Дополнительный контекст
        """
        if not self.bot:
            logger.warning("⚠️ Bot не установлен, уведомление не отправлено")
            return
        
        # Эмодзи в зависимости от severity
        severity_emoji = {
            ErrorSeverity.LOW: "ℹ️",
            ErrorSeverity.MEDIUM: "⚠️",
            ErrorSeverity.HIGH: "❌",
            ErrorSeverity.CRITICAL: "🔥"
        }
        
        # Формируем сообщение
        emoji = severity_emoji.get(severity, "⚠️")
        
        message_parts = [
            f"{emoji} <b>Ошибка в системе</b>",
            "",
            f"<b>Тип:</b> {error_type.value}",
            f"<b>Уровень:</b> {severity.value}",
            f"<b>Ошибка:</b> {type(error).__name__}",
            f"<b>Сообщение:</b> {str(error)[:500]}",  # Ограничиваем длину
        ]
        
        # Добавляем контекст
        if context:
            message_parts.append("")
            message_parts.append("<b>Контекст:</b>")
            for key, value in context.items():
                message_parts.append(f"  • {key}: {value}")
        
        # Добавляем время
        message_parts.append("")
        message_parts.append(f"<b>Время:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        # Добавляем счетчик
        error_key = f"{error_type.value}:{type(error).__name__}"
        count = self._error_counts.get(error_key, 0)
        if count > 1:
            message_parts.append(f"<b>Повторений:</b> {count}")
        
        message = "\n".join(message_parts)
        
        try:
            await self.bot.send_message(
                chat_id=self.operator_id,
                text=message
            )
            logger.info(f"✅ Уведомление оператору отправлено: {error_type.value}")
            
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление оператору: {e}")
    
    async def handle_database_error(
        self,
        error: Exception,
        operation: str,
        notify: bool = True
    ) -> None:
        """
        Обработка ошибок БД.
        
        Args:
            error: Исключение БД
            operation: Описание операции
            notify: Отправлять уведомление
        """
        await self.handle_error(
            error=error,
            error_type=ErrorType.DATABASE,
            severity=ErrorSeverity.HIGH,
            context={"operation": operation},
            notify_operator=notify
        )
    
    async def handle_api_error(
        self,
        error: Exception,
        service: str,
        endpoint: Optional[str] = None,
        notify: bool = True
    ) -> None:
        """
        Обработка ошибок внешних API.
        
        Args:
            error: Исключение API
            service: Название сервиса (OpenRouter, Telegram, etc.)
            endpoint: Эндпоинт API
            notify: Отправлять уведомление
        """
        context = {"service": service}
        if endpoint:
            context["endpoint"] = endpoint
        
        # Определяем severity в зависимости от типа ошибки
        severity = ErrorSeverity.MEDIUM
        
        # Критичные сервисы
        if service.lower() in ["database", "telegram"]:
            severity = ErrorSeverity.HIGH
        
        await self.handle_error(
            error=error,
            error_type=ErrorType.API,
            severity=severity,
            context=context,
            notify_operator=notify
        )
    
    async def handle_ai_error(
        self,
        error: Exception,
        model: str,
        task: str,
        notify: bool = False  # AI ошибки обычно не критичны
    ) -> None:
        """
        Обработка ошибок AI сервиса.
        
        Args:
            error: Исключение AI
            model: Модель AI
            task: Тип задачи
            notify: Отправлять уведомление
        """
        await self.handle_error(
            error=error,
            error_type=ErrorType.AI,
            severity=ErrorSeverity.MEDIUM,
            context={"model": model, "task": task},
            notify_operator=notify
        )
    
    async def handle_critical_error(
        self,
        error: Exception,
        component: str,
        context: Optional[dict] = None
    ) -> None:
        """
        Обработка критических ошибок (всегда с уведомлением).
        
        Args:
            error: Исключение
            component: Компонент системы
            context: Дополнительный контекст
        """
        if context is None:
            context = {}
        
        context["component"] = component
        
        await self.handle_error(
            error=error,
            error_type=ErrorType.INTERNAL,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            notify_operator=True
        )
    
    def get_error_stats(self) -> dict:
        """
        Получение статистики ошибок.
        
        Returns:
            Словарь со статистикой
        """
        return dict(self._error_counts)
    
    def reset_stats(self):
        """Сброс статистики ошибок"""
        self._error_counts.clear()
        self._error_cooldown.clear()


## Глобальный экземпляр error handler (синглтон)
_error_handler_instance: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """
    Получение глобального экземпляра ErrorHandler (синглтон).
    
    Returns:
        Экземпляр ErrorHandler
    """
    global _error_handler_instance
    
    if _error_handler_instance is None:
        _error_handler_instance = ErrorHandler()
    
    return _error_handler_instance


def set_error_handler_bot(bot: Bot):
    """
    Установить бота для error handler.
    
    Args:
        bot: Экземпляр Bot
    """
    handler = get_error_handler()
    handler.set_bot(bot)


## Декоратор для автоматической обработки ошибок
def handle_errors(
    error_type: ErrorType,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    notify: bool = True
):
    """
    Декоратор для автоматической обработки ошибок в функциях.
    
    Args:
        error_type: Тип ошибки
        severity: Уровень критичности
        notify: Отправлять уведомление
        
    Example:
        @handle_errors(ErrorType.DATABASE, ErrorSeverity.HIGH)
        async def my_db_function():
            ...
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                handler = get_error_handler()
                await handler.handle_error(
                    error=e,
                    error_type=error_type,
                    severity=severity,
                    context={"function": func.__name__},
                    notify_operator=notify
                )
                raise
        
        def sync_wrapper(*args, **kwargs):
            import asyncio
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handler = get_error_handler()
                # Для синхронных функций просто логируем
                logger.exception(f"Ошибка в {func.__name__}: {e}")
                raise
        
        # Определяем, синхронная или асинхронная функция
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


if __name__ == "__main__":
    # Тестирование обработки ошибок
    import asyncio
    
    async def test():
        handler = ErrorHandler()
        
        # Тест разных типов ошибок
        await handler.handle_database_error(
            Exception("Connection timeout"),
            operation="get_leads",
            notify=False
        )
        
        await handler.handle_api_error(
            Exception("API rate limit"),
            service="OpenRouter",
            endpoint="/chat/completions",
            notify=False
        )
        
        await handler.handle_ai_error(
            Exception("Model not available"),
            model="llama-3",
            task="score_lead",
            notify=False
        )
        
        # Статистика
        stats = handler.get_error_stats()
        print(f"\n📊 Статистика ошибок: {stats}")
        
        print("\n✅ Тестирование обработки ошибок завершено")
    
    asyncio.run(test())

