"""
## Модуль отправки сообщений через userbot
Отправляет сообщения в чаты от имени Telegram аккаунтов с антиспам механизмами.
"""

import asyncio
import random
from typing import Optional, Tuple, Dict, Any, List
from loguru import logger

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError,
    MessageTooLongError, SlowModeWaitError
)

from config import settings


## Класс для отправки сообщений через userbot
class MessageSender:
    """
    Отправляет сообщения в Telegram чаты от имени userbot аккаунтов.
    Включает антиспам механизмы и случайные задержки.
    """
    
    def __init__(self, client_manager):
        """
        Args:
            client_manager: Экземпляр ClientManager с активными клиентами
        """
        self.client_manager = client_manager
        
    async def send_message(
        self,
        account_id: int,
        chat_tg_id: int,
        message_text: str,
        reply_to_message_id: Optional[int] = None,
        author_username: Optional[str] = None,
        author_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        ## Отправить сообщение В ЛИЧКУ заказчику

        Логика:
        1. Если есть author_username — отправляем по username
        2. Если нет username но есть author_id — пробуем по ID
        3. Если ничего не сработало — NO_DM_ACCESS (оператор отправит вручную)

        Args:
            account_id: ID аккаунта в БД
            chat_tg_id: Telegram ID чата (для логов)
            message_text: Текст сообщения
            reply_to_message_id: ID сообщения (не используется)
            author_username: Username автора лида
            author_id: Telegram User ID автора лида

        Returns:
            Tuple[success, error_message]
        """
        try:
            # Получаем клиент для аккаунта
            client = self.client_manager.get_client_by_account_id(account_id)

            if not client:
                error = f"Клиент для аккаунта {account_id} не найден"
                logger.error(f"❌ {error}")
                return False, error

            if not client.is_connected():
                error = f"Клиент для аккаунта {account_id} не подключён"
                logger.error(f"❌ {error}")
                return False, error

            # Случайная задержка перед отправкой (антиспам)
            delay = random.uniform(
                settings.min_send_delay,
                settings.max_send_delay
            )

            logger.info(
                f"⏳ Задержка перед отправкой: {delay:.1f} сек "
                f"(аккаунт {account_id}, автор @{author_username or 'N/A'} id={author_id})"
            )

            await asyncio.sleep(delay)

            ## Попытка 1: по username
            if author_username:
                try:
                    logger.info(
                        f"📤 Отправка в ЛС по username: аккаунт {account_id} → @{author_username}"
                    )
                    await client.send_message(author_username, message_text)
                    logger.info(
                        f"✅ Сообщение отправлено В ЛИЧКУ: аккаунт {account_id} → @{author_username}"
                    )
                    return True, None
                except Exception as e:
                    logger.warning(
                        f"⚠️ Не удалось отправить по username @{author_username}: {type(e).__name__}: {e}"
                    )

            ## Попытка 2: по user_id (сработает если есть общая группа)
            if author_id:
                try:
                    logger.info(
                        f"📤 Отправка в ЛС по user_id: аккаунт {account_id} → {author_id}"
                    )
                    await client.send_message(author_id, message_text)
                    logger.info(
                        f"✅ Сообщение отправлено В ЛИЧКУ: аккаунт {account_id} → user_id={author_id}"
                    )
                    return True, None
                except Exception as e:
                    logger.warning(
                        f"⚠️ Не удалось отправить по user_id {author_id}: {type(e).__name__}: {e}"
                    )

            ## Ни username, ни user_id не сработали
            error = "NO_DM_ACCESS"
            logger.warning(
                f"⚠️ Не удалось отправить ЛС автору "
                f"(username={author_username}, id={author_id}). "
                f"Оператор отправит вручную."
            )
            return False, error
            
        except FloodWaitError as e:
            error = f"FloodWait: нужно подождать {e.seconds} секунд"
            logger.warning(f"⚠️ {error}")
            return False, error
            
        except ChatWriteForbiddenError:
            error = "Нет прав на отправку сообщений в этот чат"
            logger.error(f"❌ {error}")
            return False, error
            
        except UserBannedInChannelError:
            error = "Аккаунт забанен в этом чате"
            logger.error(f"❌ {error}")
            return False, error
            
        except MessageTooLongError:
            error = "Сообщение слишком длинное"
            logger.error(f"❌ {error}")
            return False, error
            
        except SlowModeWaitError as e:
            error = f"Slow mode: нужно подождать {e.seconds} секунд"
            logger.warning(f"⚠️ {error}")
            return False, error
            
        except Exception as e:
            error = f"Непредвиденная ошибка: {str(e)}"
            logger.exception(f"❌ {error}")
            return False, error
            
    def get_accounts_status(self) -> List[Dict[str, Any]]:
        """
        Получить статус всех аккаунтов.
        
        Returns:
            Список словарей со статусами аккаунтов
        """
        statuses = []
        
        for account_id, client in self.client_manager.clients.items():
            status = {
                'account_id': account_id,
                'is_connected': client.is_connected(),
                'monitored_chats_count': len(
                    self.client_manager.account_to_chats.get(account_id, [])
                )
            }
            statuses.append(status)
            
        return statuses

