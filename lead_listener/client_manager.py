"""
## Менеджер Telethon клиентов
Управляет несколькими Telegram userbot клиентами одновременно.
Распределяет чаты между клиентами и обрабатывает подключения.
"""

import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
from loguru import logger

from telethon import TelegramClient, events, functions
from telethon.errors import (
    SessionPasswordNeededError, PhoneNumberInvalidError,
    FloodWaitError, RPCError, ChannelPrivateError, ChatAdminRequiredError
)
from telethon.tl.types import User

from config import settings
from shared.database.models import Account, Chat
from lead_listener.message_handler import MessageHandler


## Класс для управления несколькими Telethon клиентами
class ClientManager:
    """
    Управляет пулом Telethon клиентов для разных аккаунтов.
    Обеспечивает подключение, переподключение и распределение нагрузки.
    """
    
    def __init__(self, notifier=None):
        self.clients: Dict[int, TelegramClient] = {}  # account_id -> client
        self.account_roles: Dict[int, str] = {}  # account_id -> role (monitor/reply/both)
        self.account_to_chats: Dict[int, List[int]] = {}  # account_id -> [chat_ids]
        self.message_handler = MessageHandler(notifier)
        
    async def add_client(self, account: Account) -> bool:
        """
        Создать и добавить Telethon клиент для аккаунта.
        
        Args:
            account: Модель аккаунта из БД
            
        Returns:
            True если клиент создан успешно
        """
        try:
            ## Используем account.id вместо tg_user_id для совместимости с AccountAuthorizer
            session_file = settings.sessions_dir / f"account_{account.id}.session"
            
            client = TelegramClient(
                str(session_file),
                settings.telegram_api_id,
                settings.telegram_api_hash,
                device_model="LeadHunter Bot",
                system_version="1.0",
                app_version="1.0"
            )
            
            # Регистрация обработчиков событий
            client.add_event_handler(
                self._create_message_handler(account.id),
                events.NewMessage()
            )
            
            self.clients[account.id] = client
            self.account_roles[account.id] = getattr(account, 'role', 'both')
            self.account_to_chats[account.id] = []
            
            logger.info(f"✅ Клиент для аккаунта '{account.label}' (ID: {account.id}) создан")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания клиента для аккаунта {account.id}: {e}")
            return False
            
    def _create_message_handler(self, account_id: int):
        """
        Создать обработчик сообщений для конкретного аккаунта.
        
        Args:
            account_id: ID аккаунта в БД
            
        Returns:
            Async функция-обработчик
        """
        async def handler(event):
            """Обработчик новых сообщений"""
            try:
                chat_id = event.chat_id

                ## Обрабатываем только чаты, назначенные ЭТОМУ аккаунту (не всем)
                ## Это предотвращает дублирование: если 2 аккаунта в одном чате,
                ## event придёт обоим, но обработает только назначенный
                my_chats = self.account_to_chats.get(account_id, [])
                if chat_id not in my_chats:
                    return

                logger.info(f"📩 Сообщение в чате {chat_id} (аккаунт {account_id})")

                # Передаём сообщение в обработчик
                await self.message_handler.process_message(event, account_id)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения (аккаунт {account_id}): {e}")
                
        return handler
        
    async def connect_all(self):
        """Подключить все клиенты к Telegram"""
        logger.info(f"🔄 Подключение {len(self.clients)} клиентов...")
        
        connect_tasks = []
        for account_id, client in self.clients.items():
            connect_tasks.append(self._connect_client(account_id, client))
            
        results = await asyncio.gather(*connect_tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        logger.info(f"✅ Подключено {success_count}/{len(self.clients)} клиентов")
        
    async def _connect_client(self, account_id: int, client: TelegramClient) -> bool:
        """
        Подключить конкретный клиент к Telegram.
        
        Args:
            account_id: ID аккаунта
            client: Telethon клиент
            
        Returns:
            True если подключение успешно
        """
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"❌ Аккаунт {account_id} не авторизован. Запустите CLI для авторизации.")
                return False
                
            # Получаем информацию о пользователе
            me = await client.get_me()
            logger.info(
                f"✅ Клиент подключён: @{me.username or 'no_username'} "
                f"(ID: {me.id}, аккаунт {account_id})"
            )

            ## Синхронизация update state с Telegram — без этого новые сообщения
            ## могут не приходить если сессия была прервана некорректно
            try:
                await client.catch_up()
                logger.info(f"✅ Update state синхронизирован (аккаунт {account_id})")
            except Exception as e:
                logger.warning(f"⚠️ catch_up не удался (аккаунт {account_id}): {e}")

            return True
            
        except FloodWaitError as e:
            logger.warning(f"⚠️ FloodWait для аккаунта {account_id}: ждём {e.seconds} секунд")
            await asyncio.sleep(e.seconds)
            return await self._connect_client(account_id, client)
            
        except RPCError as e:
            logger.error(f"❌ RPC ошибка при подключении аккаунта {account_id}: {e}")
            return False
            
        except Exception as e:
            logger.exception(f"❌ Неожиданная ошибка при подключении аккаунта {account_id}: {e}")
            return False
            
    async def subscribe_to_chats(self, chats: List[Chat]):
        """
        Подписать клиенты на мониторинг чатов.
        Распределяет чаты только между аккаунтами с ролью monitor/both.

        Args:
            chats: Список чатов для мониторинга
        """
        if not self.clients:
            logger.warning("⚠️ Нет подключённых клиентов для подписки на чаты")
            return

        ## Фильтруем только monitor/both аккаунты для мониторинга чатов
        monitor_account_ids = [
            acc_id for acc_id in self.clients.keys()
            if acc_id in self.account_roles and self.account_roles[acc_id] in ("monitor", "both")
        ]

        if not monitor_account_ids:
            logger.warning("⚠️ Нет аккаунтов с ролью monitor/both для подписки на чаты")
            return

        # Распределение чатов между monitor-аккаунтами (round-robin)
        for idx, chat in enumerate(chats):
            account_id = monitor_account_ids[idx % len(monitor_account_ids)]

            if account_id not in self.account_to_chats:
                self.account_to_chats[account_id] = []

            self.account_to_chats[account_id].append(chat.tg_chat_id)

        # Логирование распределения
        for account_id, chat_ids in self.account_to_chats.items():
            logger.info(f"📋 Аккаунт {account_id} (role={self.account_roles.get(account_id, '?')}): {len(chat_ids)} чатов для мониторинга")

        logger.info(f"✅ Распределено {len(chats)} чатов между {len(monitor_account_ids)} monitor-аккаунтами")
    
    async def process_recent_messages(self, chats: List[Chat], days_back: int = 1):
        """
        ## Обработка недавних сообщений из чатов (ретроспективно)

        Быстрый скан последних сообщений с keyword-фильтром (без AI).
        Сообщения, прошедшие keyword-фильтр, классифицируются через AI.
        ВАЖНО: не используем asyncio.wait_for — отмена iter_messages ломает Telethon-клиент.

        Args:
            chats: Список чатов для обработки
            days_back: Сколько дней назад смотреть (по умолчанию 1)
        """
        from datetime import datetime, timedelta, timezone

        if not self.clients:
            logger.warning("⚠️ Нет подключённых клиентов для обработки сообщений")
            return

        logger.info(f"🔄 Ретроспективная обработка: {len(chats)} чатов, {days_back} дней назад...")

        ## min_date — обрабатываем только сообщения новее этой даты
        min_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        total_processed = 0
        total_leads = 0

        for chat in chats:
            ## Находим аккаунт который мониторит этот чат
            account_id = None
            for acc_id, chat_ids in self.account_to_chats.items():
                if chat.tg_chat_id in chat_ids:
                    account_id = acc_id
                    break

            if not account_id or account_id not in self.clients:
                logger.debug(f"⏭️ Пропускаю чат '{chat.title}' - нет назначенного клиента")
                continue

            client = self.clients[account_id]

            try:
                count = await self._process_single_chat_messages(
                    client, chat, account_id, min_date
                )
                total_processed += count

                ## Задержка между чатами — антиспам
                await asyncio.sleep(0.5)

            except ChannelPrivateError:
                logger.warning(f"🔒 Чат '{chat.title}' приватный или удалён, пропускаю")

            except ChatAdminRequiredError:
                logger.warning(f"🔒 Нет прав на чтение чата '{chat.title}', пропускаю")

            except FloodWaitError as e:
                logger.warning(f"⏳ FloodWait {e.seconds}с при обработке чата '{chat.title}', жду...")
                await asyncio.sleep(e.seconds + 1)

            except Exception as e:
                logger.error(f"❌ Ошибка обработки чата '{chat.title}': {e}")

        logger.info(f"✅ Ретроспективная обработка завершена: {total_processed} сообщений проверено")
    
    async def _process_single_chat_messages(
        self, client: TelegramClient, chat: Chat,
        account_id: int, min_date
    ) -> int:
        """
        Ретроспективная обработка одного чата.
        Все сообщения проходят через AI-классификацию (без keyword pre-filter).
        Мягкий таймаут: выходит из цикла без отмены iter_messages (безопасно для Telethon).

        :param client: Telethon клиент
        :param chat: Модель чата из БД
        :param account_id: ID аккаунта
        :param min_date: Минимальная дата сообщений (UTC)
        :return: Количество обработанных сообщений
        """
        logger.info(f"📂 Ретро: '{chat.title}' (аккаунт {account_id})...")

        messages_count = 0
        max_per_chat = 30
        SOFT_TIMEOUT = 180  ## секунд — мягкий выход без отмены корутины

        start_time = asyncio.get_event_loop().time()

        ## Используем tg_chat_id напрямую — надёжнее после рестарта (кеш entity пустой)
        entity = chat.tg_chat_id

        try:
            async for message in client.iter_messages(
                entity,
                limit=max_per_chat,
                reverse=False
            ):
                ## Мягкий таймаут — graceful exit без отмены iter_messages
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > SOFT_TIMEOUT:
                    logger.warning(f"⏰ Мягкий таймаут ({SOFT_TIMEOUT}с) для '{chat.title}', обработано {messages_count}")
                    break

                ## Пропускаем сообщения старше min_date
                if message.date and message.date < min_date:
                    break

                if not message.text:
                    continue

                messages_count += 1

                ## AI-классификация каждого сообщения
                await self.message_handler.process_message_direct(
                    message=message,
                    chat_id=chat.tg_chat_id,
                    account_id=account_id
                )

        except Exception as e:
            logger.error(f"❌ Ошибка iter_messages для '{chat.title}': {e}")

        if messages_count > 0:
            logger.info(f"✅ '{chat.title}': {messages_count} сообщений обработано через AI")
        else:
            logger.debug(f"📭 '{chat.title}': нет новых сообщений")

        return messages_count

    async def join_chats(self, chats: List[Chat], use_existing_distribution: bool = True) -> Dict[str, Any]:
        """
        ## Массовая подписка рабочих аккаунтов на список чатов
        
        По умолчанию использует существующее распределение из subscribe_to_chats().
        Каждый аккаунт подписывается только на те чаты, которые он мониторит.
        
        Args:
            chats: Список чатов для подписки
            use_existing_distribution: Использовать распределение из account_to_chats (по умолчанию True)
            
        Returns:
            Статистика: успешно, ошибки, уже подписаны
        """
        from telethon.errors import (
            ChannelPrivateError, InviteHashExpiredError, 
            UserAlreadyParticipantError, FloodWaitError,
            ChatWriteForbiddenError
        )
        
        if not self.clients:
            logger.warning("⚠️ Нет подключённых клиентов для подписки")
            return {
                "success": [], "already_joined": [], "errors": [],
                "private": [], "flood_wait": [], "pending_approval": []
            }
        
        results = {
            "success": [],
            "already_joined": [],
            "errors": [],
            "private": [],
            "flood_wait": [],
            "pending_approval": []  ## Ожидают одобрения заявки
        }
        
        ## Фильтруем только monitor/both аккаунты для подписки на чаты
        monitor_clients = {
            acc_id: client for acc_id, client in self.clients.items()
            if self.account_roles.get(acc_id, 'both') in ("monitor", "both")
        }

        if not monitor_clients:
            logger.warning("⚠️ Нет аккаунтов с ролью monitor/both для подписки на чаты")
            return results

        ## Перед подпиской ОБНОВЛЯЕМ распределение чатов
        # Это нужно, если чаты были добавлены после запуска Lead Listener
        if use_existing_distribution:
            # Проверяем какие чаты не входят в текущее распределение
            all_monitored_ids = set()
            for chat_ids in self.account_to_chats.values():
                all_monitored_ids.update(chat_ids)

            new_chats = [c for c in chats if c.tg_chat_id not in all_monitored_ids]

            if new_chats:
                logger.info(f"📝 Добавляю {len(new_chats)} новых чатов в распределение...")

                ## Умное распределение: только monitor/both аккаунты
                account_ids = list(monitor_clients.keys())
                
                for chat in new_chats:
                    assigned_account = None
                    
                    # Проверяем monitor-аккаунты — может кто-то уже подписан?
                    for account_id in account_ids:
                        try:
                            client = monitor_clients[account_id]
                            
                            if chat.username:
                                entity = await client.get_entity(chat.username)
                            else:
                                entity = await client.get_entity(chat.tg_chat_id)
                            
                            # Проверяем участие в чате
                            from telethon.tl.functions.channels import GetParticipantRequest
                            from telethon.tl.types import Channel
                            
                            if isinstance(entity, Channel):
                                try:
                                    me = await client.get_me()
                                    await client(GetParticipantRequest(
                                        channel=entity,
                                        participant=me
                                    ))
                                    # Если дошли сюда - аккаунт УЖЕ подписан!
                                    assigned_account = account_id
                                    logger.info(f"✓ Аккаунт {account_id} уже подписан на '{chat.title}', назначаю ему")
                                    break
                                except Exception:
                                    # Не участник - идём дальше
                                    pass
                        except Exception as e:
                            logger.debug(f"Не удалось проверить подписку аккаунта {account_id} на '{chat.title}': {e}")
                            continue
                    
                    # Если никто не подписан - распределяем по round-robin
                    if not assigned_account:
                        assigned_account = account_ids[new_chats.index(chat) % len(account_ids)]
                        logger.debug(f"➕ Чат '{chat.title}' → Аккаунт {assigned_account} (round-robin)")
                    
                    # Добавляем в распределение
                    if assigned_account not in self.account_to_chats:
                        self.account_to_chats[assigned_account] = []
                    self.account_to_chats[assigned_account].append(chat.tg_chat_id)
        
        # Выбираем стратегию распределения
        if use_existing_distribution and self.account_to_chats:
            # Используем существующее распределение (один аккаунт → свои чаты)
            logger.info(f"🔄 Начинаю подписку используя существующее распределение чатов...")
            
            for account_id, monitored_chat_ids in self.account_to_chats.items():
                if account_id not in monitor_clients:
                    continue

                client = monitor_clients[account_id]
                
                # Подписываем только на те чаты, которые этот аккаунт мониторит
                for chat in chats:
                    if chat.tg_chat_id not in monitored_chat_ids:
                        continue  # Этот аккаунт не мониторит этот чат

                    logger.debug(f"📍 Чат '{chat.title}' → Аккаунт {account_id} (existing distribution)")
                    try:
                        await self._join_single_chat(client, account_id, chat, results)
                    except FloodWaitError:
                        ## FloodWait уже отожган внутри _join_single_chat, повторяем
                        try:
                            await self._join_single_chat(client, account_id, chat, results)
                        except FloodWaitError as e2:
                            results["flood_wait"].append({
                                "account_id": account_id, "chat": chat.title,
                                "username": chat.username, "wait_seconds": e2.seconds
                            })
                    
        else:
            # Round-robin распределение (fallback если нет существующего)
            monitor_ids = list(monitor_clients.keys())
            logger.info(f"🔄 Начинаю подписку на {len(chats)} чатов (round-robin между {len(monitor_ids)} monitor-аккаунтами)...")

            for idx, chat in enumerate(chats):
                account_id = monitor_ids[idx % len(monitor_ids)]
                client = monitor_clients[account_id]

                logger.debug(f"📍 Чат '{chat.title}' → Аккаунт {account_id} (round-robin)")
                try:
                    await self._join_single_chat(client, account_id, chat, results)
                except FloodWaitError:
                    try:
                        await self._join_single_chat(client, account_id, chat, results)
                    except FloodWaitError as e2:
                        results["flood_wait"].append({
                            "account_id": account_id, "chat": chat.title,
                            "username": chat.username, "wait_seconds": e2.seconds
                        })
        
        logger.info(
            f"✅ Подписка завершена: {len(results['success'])} успешно, "
            f"{len(results['already_joined'])} уже подписаны, "
            f"{len(results['errors'])} ошибок"
        )
        
        return results
    
    async def _join_single_chat(self, client: TelegramClient, account_id: int, 
                                 chat: Chat, results: Dict[str, Any]):
        """
        ## Вспомогательный метод для подписки одного аккаунта на один чат
        """
        from telethon.errors import (
            ChannelPrivateError, InviteHashExpiredError, 
            UserAlreadyParticipantError, FloodWaitError,
            ChatWriteForbiddenError, UserIsBlockedError,
            InviteRequestSentError
        )
        
        try:
            # Пробуем получить entity чата
            if chat.username:
                entity = await client.get_entity(chat.username)
            else:
                entity = await client.get_entity(chat.tg_chat_id)
            
            # Проверяем тип чата
            from telethon.tl.types import Channel, Chat as TgChat
            
            if isinstance(entity, Channel):
                # Канал или супергруппа
                try:
                    await client(functions.channels.JoinChannelRequest(entity))
                    
                    ## Отключаем уведомления после успешной подписки
                    await self._mute_chat_notifications(client, entity, account_id, chat.title)
                    
                    results["success"].append({
                        "account_id": account_id,
                        "chat": chat.title,
                        "username": chat.username
                    })
                    logger.info(f"✅ Аккаунт {account_id} подписался на {chat.title}")
                    
                except UserAlreadyParticipantError:
                    ## Даже если уже подписаны, отключаем уведомления
                    await self._mute_chat_notifications(client, entity, account_id, chat.title)
                    
                    results["already_joined"].append({
                        "account_id": account_id,
                        "chat": chat.title
                    })
                    logger.debug(f"⏭️ Аккаунт {account_id} уже подписан на {chat.title}")
                    
            elif isinstance(entity, TgChat):
                # Обычная группа - нужна invite ссылка
                if chat.invite_link:
                    try:
                        await client(functions.messages.ImportChatInviteRequest(
                            hash=chat.invite_link.split('/')[-1]
                        ))
                        
                        ## Отключаем уведомления после вступления
                        await self._mute_chat_notifications(client, entity, account_id, chat.title)
                        
                        results["success"].append({
                            "account_id": account_id,
                            "chat": chat.title
                        })
                        logger.info(f"✅ Аккаунт {account_id} вступил в группу {chat.title}")
                        
                    except UserAlreadyParticipantError:
                        ## Даже если уже состоим, отключаем уведомления
                        await self._mute_chat_notifications(client, entity, account_id, chat.title)
                        
                        results["already_joined"].append({
                            "account_id": account_id,
                            "chat": chat.title
                        })
                        
                else:
                    results["errors"].append({
                        "account_id": account_id,
                        "chat": chat.title,
                        "username": chat.username,
                        "error": "Нет invite_link для обычной группы"
                    })
            
            # Небольшая задержка между подписками (антиспам)
            await asyncio.sleep(2)
            
        except ChannelPrivateError:
            results["private"].append({
                "account_id": account_id,
                "chat": chat.title,
                "username": chat.username,
                "error": "Приватный канал, нужна invite-ссылка"
            })
            logger.warning(f"⚠️ {chat.title} - приватный канал")
            
        except FloodWaitError as e:
            ## При FloodWait <= 600с ждём и пробрасываем наверх для retry
            ## При > 600с просто записываем как ошибку
            if e.seconds <= 600:
                logger.warning(f"⏳ FloodWait {e.seconds}s для аккаунта {account_id} на '{chat.title}', жду...")
                await asyncio.sleep(e.seconds + 2)
                raise  # Пробрасываем — вызывающий код сделает retry
            results["flood_wait"].append({
                "account_id": account_id,
                "chat": chat.title,
                "username": chat.username,
                "wait_seconds": e.seconds
            })
            logger.warning(f"⏳ FloodWait {e.seconds}s слишком долго, пропускаю '{chat.title}'")
        
        except InviteRequestSentError:
            ## Заявка уже была подана ранее, ожидает одобрения
            results["pending_approval"].append({
                "account_id": account_id,
                "chat": chat.title,
                "username": chat.username,
                "status": "already_sent"
            })
            logger.info(f"⏳ Заявка на {chat.title} уже подана (аккаунт {account_id}), ожидает одобрения")
            
        except Exception as e:
            error_str = str(e)
            
            ## Проверяем нужна ли заявка на вступление
            # Telegram может вернуть разные ошибки когда требуется заявка
            needs_request = any(keyword in error_str.lower() for keyword in [
                'request', 'approval', 'join request', 'invite request',
                'you need to join', 'send a request', 'successfully requested'
            ])
            
            # Также проверяем "ResolveUsernameRequest" - может быть нужна заявка
            is_resolve_error = 'ResolveUsernameRequest' in error_str or 'key is not registered' in error_str.lower()
            
            if needs_request or 'JoinAsPeerRequest' in error_str or (is_resolve_error and chat.username):
                ## Пытаемся автоматически подать заявку через username
                if not chat.username:
                    # Нет username - не можем подать заявку
                    results["errors"].append({
                        "account_id": account_id,
                        "chat": chat.title,
                        "username": chat.username,
                        "error": f"Требуется заявка, но нет username: {error_str[:80]}"
                    })
                else:
                    try:
                        logger.info(f"📝 Подаю заявку на вступление в {chat.title} через @{chat.username} (аккаунт {account_id})...")
                        
                        ## Пытаемся несколькими способами получить entity
                        entity_to_join = None
                        
                        # Способ 1: Через ResolveUsernameRequest
                        from telethon.tl.functions.contacts import ResolveUsernameRequest
                        try:
                            resolved = await client(ResolveUsernameRequest(chat.username))
                            if resolved.chats:
                                entity_to_join = resolved.chats[0]
                                logger.debug(f"✅ Entity получен через ResolveUsername")
                        except Exception as resolve_err:
                            logger.debug(f"⚠️ ResolveUsername не сработал: {resolve_err}")
                        
                        # Способ 2: Через get_entity с username
                        if not entity_to_join:
                            try:
                                entity_to_join = await client.get_entity(f"@{chat.username}")
                                logger.debug(f"✅ Entity получен через get_entity(@username)")
                            except Exception as get_err:
                                logger.debug(f"⚠️ get_entity не сработал: {get_err}")
                        
                        # Способ 3: Через get_entity с https://t.me/username
                        if not entity_to_join:
                            try:
                                entity_to_join = await client.get_entity(f"https://t.me/{chat.username}")
                                logger.debug(f"✅ Entity получен через get_entity(t.me link)")
                            except Exception as link_err:
                                logger.debug(f"⚠️ get_entity(link) не сработал: {link_err}")
                        
                        # Если удалось получить entity - пытаемся вступить
                        if entity_to_join:
                            try:
                                await client(functions.channels.JoinChannelRequest(entity_to_join))
                                
                                results["pending_approval"].append({
                                    "account_id": account_id,
                                    "chat": chat.title,
                                    "username": chat.username,
                                    "status": "request_sent"
                                })
                                logger.info(f"✅ Заявка подана на {chat.title} (аккаунт {account_id})")
                                
                            except InviteRequestSentError:
                                # Заявка подана успешно!
                                results["pending_approval"].append({
                                    "account_id": account_id,
                                    "chat": chat.title,
                                    "username": chat.username,
                                    "status": "request_sent"
                                })
                                logger.info(f"✅ Заявка подана на {chat.title} (аккаунт {account_id})")
                        else:
                            # Не удалось получить entity ни одним способом
                            raise ValueError(f"Не удалось получить entity для @{chat.username}")
                        
                    except Exception as request_error:
                        error_msg = str(request_error)
                        # Проверяем успешно ли подана заявка по тексту ошибки
                        if 'successfully requested' in error_msg.lower():
                            results["pending_approval"].append({
                                "account_id": account_id,
                                "chat": chat.title,
                                "username": chat.username,
                                "status": "request_sent"
                            })
                            logger.info(f"✅ Заявка подана на {chat.title} (аккаунт {account_id})")
                        else:
                            logger.warning(f"⚠️ Не удалось подать заявку на {chat.title}: {request_error}")
                            results["errors"].append({
                                "account_id": account_id,
                                "chat": chat.title,
                                "username": chat.username,
                                "error": f"Не удалось подать заявку: {error_msg[:80]}"
                            })
            else:
                ## Обычная ошибка
                results["errors"].append({
                    "account_id": account_id,
                    "chat": chat.title,
                    "username": chat.username,
                    "error": error_str
                })
                logger.error(f"❌ Ошибка подписки на {chat.title}: {e}")
    
    async def _mute_chat_notifications(self, client: TelegramClient, entity, 
                                        account_id: int, chat_title: str):
        """
        ## Отключение уведомлений для чата
        
        Args:
            client: Telethon клиент
            entity: Entity чата (Channel или Chat)
            account_id: ID аккаунта (для логирования)
            chat_title: Название чата (для логирования)
        """
        try:
            from telethon.tl.types import InputPeerNotifySettings
            
            # Настройки для отключения уведомлений
            mute_settings = InputPeerNotifySettings(
                show_previews=False,
                silent=True,
                mute_until=2**31 - 1  # Максимальное значение (навсегда)
            )
            
            # Применяем настройки
            await client(functions.account.UpdateNotifySettingsRequest(
                peer=entity,
                settings=mute_settings
            ))
            
            logger.debug(f"🔕 Уведомления отключены для '{chat_title}' (аккаунт {account_id})")
            
        except Exception as e:
            # Не критичная ошибка, просто логируем
            logger.warning(f"⚠️ Не удалось отключить уведомления для '{chat_title}': {e}")
        
    async def disconnect_all(self):
        """Отключить все клиенты"""
        logger.info("🔄 Отключение всех клиентов...")
        
        for account_id, client in self.clients.items():
            try:
                if client.is_connected():
                    await client.disconnect()
                    logger.info(f"✅ Клиент аккаунта {account_id} отключён")
            except Exception as e:
                logger.error(f"❌ Ошибка отключения клиента {account_id}: {e}")
                
    async def run_until_disconnected(self):
        """Держать все клиенты активными до принудительной остановки"""
        logger.info("🎧 Прослушивание сообщений...")

        ## Создаём задачи только для авторизованных клиентов
        ## ВАЖНО: Нужно создавать Task объекты, а не просто корутины
        tasks = []
        for account_id, client in self.clients.items():
            try:
                # Подключаемся если не подключены
                if not client.is_connected():
                    await client.connect()

                # Проверяем авторизацию перед созданием задачи
                if await client.is_user_authorized():
                    task = asyncio.create_task(
                        self._safe_run_until_disconnected(account_id, client)
                    )
                    tasks.append(task)
                else:
                    logger.debug(f"⏭️ Пропускаем неавторизованный аккаунт {account_id}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка проверки авторизации аккаунта {account_id}: {e}")
        
        # Если нет авторизованных клиентов - просто ждём бесконечно
        if not tasks:
            logger.info("⏳ Нет активных авторизованных клиентов. Ожидание добавления...")
            # Создаём событие и ждём его бесконечно (оно никогда не случится)
            stop_event = asyncio.Event()
            await stop_event.wait()
        else:
            ## Ждём завершения ВСЕХ клиентов — падение одного не убивает остальных
            await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
    
    async def _safe_run_until_disconnected(self, account_id: int, client: TelegramClient):
        """
        Безопасный запуск run_until_disconnected с обработкой ошибок.
        
        Args:
            account_id: ID аккаунта
            client: Telethon клиент
        """
        try:
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Ошибка в клиенте аккаунта {account_id}: {e}")
            # Не пробрасываем исключение дальше, чтобы не падал весь сервис
        
    def get_client_by_account_id(self, account_id: int) -> Optional[TelegramClient]:
        """
        Получить Telethon клиент по ID аккаунта.
        
        Args:
            account_id: ID аккаунта в БД
            
        Returns:
            TelegramClient или None
        """
        return self.clients.get(account_id)

