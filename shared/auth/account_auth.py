"""
## Модуль авторизации Telegram аккаунтов
Универсальный модуль для авторизации аккаунтов через Telethon.
Можно использовать из Admin Bot и из CLI.
"""

import asyncio
from pathlib import Path
from typing import Optional, Callable, Awaitable

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    AuthKeyUnregisteredError
)

from config import settings
from shared.database.engine import get_session
from shared.database.crud import get_account_by_id, update_account_tg_data


## Класс для авторизации аккаунта
class AccountAuthorizer:
    """
    Класс для авторизации Telegram аккаунтов через Telethon.
    Поддерживает интерактивный и программный режимы.
    """
    
    def __init__(
        self,
        account_id: int,
        phone: str,
        on_code_request: Optional[Callable[[], Awaitable[str]]] = None,
        on_password_request: Optional[Callable[[], Awaitable[str]]] = None
    ):
        """
        Инициализация авторизатора.
        
        Args:
            account_id: ID аккаунта в БД
            phone: Номер телефона
            on_code_request: Callback для запроса кода (возвращает код)
            on_password_request: Callback для запроса 2FA пароля (возвращает пароль)
        """
        self.account_id = account_id
        self.phone = phone
        self.on_code_request = on_code_request
        self.on_password_request = on_password_request
        self.client: Optional[TelegramClient] = None
        
    async def authorize(self, password: Optional[str] = None) -> tuple[bool, Optional[str], Optional[int], Optional[str]]:
        """
        Авторизует аккаунт.
        
        Args:
            password: Пароль 2FA (если требуется)
        
        Returns:
            Кортеж (success, error_message, tg_user_id, username)
        """
        # Создаём временный файл сессии
        session_file = settings.sessions_dir / f"temp_auth_{self.account_id}.session"
        
        try:
            # Если клиент уже создан и подключён, используем его
            if self.client and self.client.is_connected():
                # Клиент уже подключён - проверяем авторизацию
                if await self.client.is_user_authorized():
                    me = await self.client.get_me()
                    
                    ## Отключаем клиент ПЕРЕД переносом файла
                    await self.client.disconnect()
                    
                    # Обновляем данные в БД
                    async with get_session() as session:
                        await update_account_tg_data(
                            session,
                            self.account_id,
                            tg_user_id=me.id,
                            username=me.username
                        )
                        await session.commit()
                    
                    # Перемещаем сессию в постоянный файл
                    final_session = settings.sessions_dir / f"account_{self.account_id}.session"
                    if session_file.exists():
                        session_file.rename(final_session)
                    
                    return True, None, me.id, me.username
                
                # Клиент подключён, но не авторизован - вводим пароль
                if password:
                    await self.client.sign_in(password=password)
                    me = await self.client.get_me()
                    
                    ## Отключаем клиент ПЕРЕД переносом файла
                    await self.client.disconnect()
                    
                    # Обновляем данные в БД
                    async with get_session() as session:
                        await update_account_tg_data(
                            session,
                            self.account_id,
                            tg_user_id=me.id,
                            username=me.username
                        )
                        await session.commit()
                    
                    # Перемещаем сессию в постоянный файл
                    final_session = settings.sessions_dir / f"account_{self.account_id}.session"
                    if session_file.exists():
                        session_file.rename(final_session)
                    
                    return True, None, me.id, me.username
                else:
                    return False, "NEEDS_PASSWORD", None, None
            
            # Создаём Telethon клиент
            self.client = TelegramClient(
                str(session_file),
                settings.telegram_api_id,
                settings.telegram_api_hash
            )
            
            await self.client.connect()
            
            # Проверяем, не авторизован ли уже
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                
                ## Отключаем клиент ПЕРЕД переносом файла
                await self.client.disconnect()
                
                # Обновляем данные в БД
                async with get_session() as session:
                    await update_account_tg_data(
                        session,
                        self.account_id,
                        tg_user_id=me.id,
                        username=me.username
                    )
                    await session.commit()
                
                # Перемещаем сессию в постоянный файл
                final_session = settings.sessions_dir / f"account_{self.account_id}.session"
                if session_file.exists():
                    session_file.rename(final_session)
                
                return True, None, me.id, me.username
            
            # Отправляем код авторизации
            if not self.on_code_request:
                return False, "Callback для запроса кода не установлен", None, None
            
            await self.client.send_code_request(self.phone)
            code = await self.on_code_request()
            
            if not code:
                return False, "Код не получен", None, None
            
            # Вводим код
            try:
                await self.client.sign_in(self.phone, code)
            except SessionPasswordNeededError:
                # Нужен 2FA пароль
                if password:
                    # Пароль передан - используем его
                    await self.client.sign_in(password=password)
                else:
                    # Пароль не передан - возвращаем специальный статус
                    return False, "NEEDS_PASSWORD", None, None
            
            # Получаем информацию о пользователе
            me = await self.client.get_me()
            
            # Отключаем клиент ПЕРЕД переносом файла сессии
            await self.client.disconnect()
            
            # Обновляем данные в БД
            async with get_session() as session:
                await update_account_tg_data(
                    session,
                    self.account_id,
                    tg_user_id=me.id,
                    username=me.username
                )
                await session.commit()
            
            # Перемещаем сессию в постоянный файл
            final_session = settings.sessions_dir / f"account_{self.account_id}.session"
            if session_file.exists():
                session_file.rename(final_session)
            
            return True, None, me.id, me.username
            
        except PhoneNumberInvalidError:
            return False, "Неверный номер телефона", None, None
        except PhoneCodeInvalidError:
            return False, "Неверный код авторизации", None, None
        except PhoneCodeExpiredError:
            return False, "Код авторизации истёк", None, None
        except FloodWaitError as e:
            return False, f"Слишком много попыток. Подождите {e.seconds} секунд", None, None
        except AuthKeyUnregisteredError:
            return False, "Сессия не зарегистрирована. Попробуйте снова", None, None
        except Exception as e:
            return False, f"Неожиданная ошибка: {str(e)}", None, None
        finally:
            if self.client and self.client.is_connected():
                await self.client.disconnect()

