"""
## CLI утилита для авторизации Telegram аккаунтов
Интерактивная утилита для логина userbot-аккаунтов через терминал.
"""

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, PhoneNumberInvalidError,
    PhoneCodeInvalidError, PhoneCodeExpiredError,
    FloodWaitError
)

from config import settings
from shared.database.engine import get_session, init_db
from shared.database.crud import (
    create_account, get_account_by_tg_id, get_all_accounts,
    get_account_by_id, update_account_tg_data, update_account_status,
)
from shared.database.models import CommunicationStyle


## Класс для интерактивной авторизации аккаунтов
class AuthCLI:
    """
    CLI интерфейс для авторизации Telegram userbot аккаунтов.
    """
    
    def __init__(self):
        self.client: TelegramClient = None
        
    async def start(self):
        """Запустить интерактивное меню авторизации"""
        logger.remove()  # Убираем логи для чистого вывода
        
        print("=" * 60)
        print("🔐 LeadHunter - Авторизация Telegram аккаунтов")
        print("=" * 60)
        print()
        
        # Инициализация БД
        await init_db()
        
        while True:
            print("\n📋 Главное меню:")
            print("  1. Авторизовать существующий аккаунт")
            print("  2. Добавить новый аккаунт")
            print("  3. Просмотреть аккаунты")
            print("  4. Удалить аккаунт")
            print("  0. Выход")
            print()

            choice = input("Выберите действие: ").strip()

            if choice == '1':
                await self._auth_existing_account()
            elif choice == '2':
                await self._add_account()
            elif choice == '3':
                await self._list_accounts()
            elif choice == '4':
                await self._remove_account()
            elif choice == '0':
                print("\n👋 До свидания!")
                break
            else:
                print("❌ Неверный выбор. Попробуйте ещё раз.")
                
    async def _auth_existing_account(self):
        """Авторизовать существующий аккаунт (уже добавленный через бот)"""
        print("\n" + "=" * 60)
        print("🔑 Авторизация существующего аккаунта")
        print("=" * 60)

        ## Показываем неавторизованные аккаунты (tg_user_id == 0 или disabled)
        async with get_session() as session:
            accounts = await get_all_accounts(session)

        if not accounts:
            print("\n⚠️ Нет аккаунтов в БД. Сначала добавьте через бот или пункт 2.")
            return

        ## Фильтруем неавторизованные
        unauthed = [a for a in accounts if a.tg_user_id == 0 or not a.enabled]

        print("\n📋 Аккаунты, требующие авторизации:")
        if unauthed:
            for a in unauthed:
                print(f"  🆔 {a.id} | {a.label} | 📞 {a.phone or '?'} | tg_id={a.tg_user_id}")
        else:
            print("  ✅ Все аккаунты авторизованы!")
            print("\n📋 Все аккаунты:")
            for a in accounts:
                status = "✅" if a.enabled else "❌"
                print(f"  {status} 🆔 {a.id} | {a.label} | 📞 {a.phone or '?'} | tg_id={a.tg_user_id}")

        account_id = input("\nВведите ID аккаунта для авторизации (0 для отмены): ").strip()

        try:
            account_id = int(account_id)
        except ValueError:
            print("❌ Неверный ID")
            return

        if account_id == 0:
            print("❌ Отменено")
            return

        ## Получаем аккаунт
        async with get_session() as session:
            account = await get_account_by_id(session, account_id)

        if not account:
            print(f"❌ Аккаунт с ID {account_id} не найден")
            return

        phone = account.phone
        if not phone:
            phone = input("📞 Номер телефона не указан. Введите (например +79991234567): ").strip()
            if not phone.startswith('+'):
                print("❌ Номер должен начинаться с '+'")
                return

        print(f"\n🔄 Авторизация аккаунта '{account.label}' ({phone})...")

        ## Создаём Telethon клиент
        session_file = settings.sessions_dir / f"temp_auth_{phone.replace('+', '')}.session"

        try:
            self.client = TelegramClient(
                str(session_file),
                settings.telegram_api_id,
                settings.telegram_api_hash
            )

            await self.client.connect()

            if await self.client.is_user_authorized():
                print("✅ Уже авторизован!")
                me = await self.client.get_me()
            else:
                print("📨 Отправка кода авторизации...")
                await self.client.send_code_request(phone)

                code = input("📨 Введите код из Telegram: ").strip()

                try:
                    await self.client.sign_in(phone, code)
                    me = await self.client.get_me()
                except SessionPasswordNeededError:
                    password = input("🔒 Введите пароль 2FA: ").strip()
                    await self.client.sign_in(password=password)
                    me = await self.client.get_me()

            print(f"\n✅ Авторизация успешна!")
            print(f"   👤 Имя: {me.first_name} {me.last_name or ''}")
            print(f"   🆔 Telegram ID: {me.id}")
            print(f"   📝 Username: @{me.username or 'не установлен'}")

            ## Обновляем аккаунт в БД
            async with get_session() as session:
                await update_account_tg_data(session, account_id, tg_user_id=me.id, username=me.username)
                await update_account_status(session, account_id, enabled=True)
                await session.commit()

            ## Переименовываем сессию в формат ClientManager: account_{db_id}.session
            final_session = settings.sessions_dir / f"account_{account_id}.session"
            if final_session.exists():
                final_session.unlink()
            session_file.rename(final_session)

            print(f"\n✅ Аккаунт '{account.label}' авторизован и активирован!")
            print(f"   📁 Сессия: account_{account_id}.session")

        except PhoneNumberInvalidError:
            print("❌ Неверный номер телефона")
        except PhoneCodeInvalidError:
            print("❌ Неверный код авторизации")
        except PhoneCodeExpiredError:
            print("❌ Код авторизации истёк. Попробуйте снова.")
        except FloodWaitError as e:
            print(f"❌ Слишком много попыток. Подождите {e.seconds} секунд.")
        except Exception as e:
            logger.exception(f"❌ Ошибка авторизации: {e}")
            print(f"❌ Произошла ошибка: {e}")
        finally:
            if self.client:
                await self.client.disconnect()

    async def _add_account(self):
        """Добавить новый аккаунт через авторизацию"""
        print("\n" + "=" * 60)
        print("📱 Добавление нового аккаунта")
        print("=" * 60)
        
        # Ввод номера телефона
        phone = input("\nВведите номер телефона (в международном формате, например +79991234567): ").strip()
        
        if not phone.startswith('+'):
            print("❌ Номер должен начинаться с '+'")
            return
            
        # Ввод метки аккаунта
        label = input("Введите название аккаунта (например, 'Рабочий 1'): ").strip()
        
        if not label:
            print("❌ Название не может быть пустым")
            return
            
        # Выбор стиля по умолчанию
        print("\n📝 Выберите стиль общения по умолчанию:")
        print("  1. Вежливый/деловой (polite)")
        print("  2. Неформальный/дружеский (friendly)")
        print("  3. Агрессивный/жёсткий (aggressive)")
        
        style_choice = input("Ваш выбор (по умолчанию 2): ").strip() or '2'
        
        style_map = {
            '1': CommunicationStyle.POLITE.value,
            '2': CommunicationStyle.FRIENDLY.value,
            '3': CommunicationStyle.AGGRESSIVE.value
        }
        
        style = style_map.get(style_choice, CommunicationStyle.FRIENDLY.value)
        
        # Создание Telethon клиента
        session_file = settings.sessions_dir / f"temp_auth_{phone.replace('+', '')}.session"
        
        try:
            self.client = TelegramClient(
                str(session_file),
                settings.telegram_api_id,
                settings.telegram_api_hash
            )
            
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                print("✅ Аккаунт уже авторизован")
                me = await self.client.get_me()
            else:
                # Запрос кода авторизации
                print("\n🔄 Отправка кода авторизации...")
                await self.client.send_code_request(phone)
                
                code = input("📨 Введите код из Telegram: ").strip()
                
                try:
                    # Попытка входа с кодом
                    await self.client.sign_in(phone, code)
                    me = await self.client.get_me()
                    
                except SessionPasswordNeededError:
                    # Нужен двухфакторный пароль
                    password = input("🔒 Введите пароль 2FA: ").strip()
                    await self.client.sign_in(password=password)
                    me = await self.client.get_me()
                    
            # Успешная авторизация
            print(f"\n✅ Авторизация успешна!")
            print(f"   👤 Имя: {me.first_name} {me.last_name or ''}")
            print(f"   🆔 ID: {me.id}")
            print(f"   📝 Username: @{me.username or 'не установлен'}")
            
            # Сохранение в БД
            async with get_session() as session:
                # Проверяем, не существует ли уже
                existing = await get_account_by_tg_id(session, me.id)
                
                if existing:
                    print(f"\n⚠️ Аккаунт с ID {me.id} уже существует в БД (label: '{existing.label}')")
                    overwrite = input("Перезаписать? (y/n): ").strip().lower()
                    
                    if overwrite != 'y':
                        print("❌ Отменено")
                        return
                        
                    # Удаляем старый
                    from shared.database.crud import delete_account
                    await delete_account(session, existing.id)
                    await session.commit()
                    
                # Создаём новый аккаунт
                account = await create_account(
                    session=session,
                    label=label,
                    tg_user_id=me.id,
                    phone=phone,
                    username=me.username,
                    style_default=style,
                    enabled=True
                )
                
                await session.commit()
                
                # Переименовываем сессию
                final_session = settings.sessions_dir / f"session_{me.id}.session"
                session_file.rename(final_session)
                
                print(f"\n✅ Аккаунт '{label}' успешно добавлен в систему!")
                print(f"   🆔 ID в БД: {account.id}")
                print(f"   📱 Telegram ID: {account.tg_user_id}")
                print(f"   🎨 Стиль: {account.style_default}")
                
        except PhoneNumberInvalidError:
            print("❌ Неверный номер телефона")
        except PhoneCodeInvalidError:
            print("❌ Неверный код авторизации")
        except PhoneCodeExpiredError:
            print("❌ Код авторизации истёк. Попробуйте снова.")
        except FloodWaitError as e:
            print(f"❌ Слишком много попыток. Подождите {e.seconds} секунд.")
        except Exception as e:
            logger.exception(f"❌ Ошибка авторизации: {e}")
            print(f"❌ Произошла ошибка: {e}")
        finally:
            if self.client:
                await self.client.disconnect()
                
    async def _list_accounts(self):
        """Показать список всех аккаунтов"""
        print("\n" + "=" * 60)
        print("📋 Список аккаунтов")
        print("=" * 60)
        
        async with get_session() as session:
            accounts = await get_all_accounts(session)
            
            if not accounts:
                print("\n⚠️ Нет зарегистрированных аккаунтов")
                return
                
            for account in accounts:
                status = "✅ Активен" if account.enabled else "❌ Отключён"
                print(f"\n🆔 ID: {account.id}")
                print(f"   📛 Название: {account.label}")
                print(f"   📱 Telegram ID: {account.tg_user_id}")
                print(f"   👤 Username: @{account.username or 'не установлен'}")
                print(f"   📞 Телефон: {account.phone or 'не указан'}")
                print(f"   🎨 Стиль: {account.style_default}")
                print(f"   📊 Статус: {status}")
                print(f"   📅 Создан: {account.created_at.strftime('%d.%m.%Y %H:%M')}")
                
    async def _remove_account(self):
        """Удалить аккаунт"""
        print("\n" + "=" * 60)
        print("🗑️ Удаление аккаунта")
        print("=" * 60)
        
        # Показываем список
        await self._list_accounts()
        
        account_id = input("\nВведите ID аккаунта для удаления (0 для отмены): ").strip()
        
        try:
            account_id = int(account_id)
            
            if account_id == 0:
                print("❌ Отменено")
                return
                
            async with get_session() as session:
                from shared.database.crud import get_account_by_id, delete_account
                
                account = await get_account_by_id(session, account_id)
                
                if not account:
                    print(f"❌ Аккаунт с ID {account_id} не найден")
                    return
                    
                confirm = input(f"⚠️ Удалить аккаунт '{account.label}'? (yes/no): ").strip().lower()
                
                if confirm != 'yes':
                    print("❌ Отменено")
                    return
                    
                # Удаляем из БД
                await delete_account(session, account_id)
                await session.commit()
                
                # Удаляем файл сессии
                session_file = settings.sessions_dir / f"session_{account.tg_user_id}.session"
                if session_file.exists():
                    session_file.unlink()
                    
                print(f"✅ Аккаунт '{account.label}' успешно удалён")
                
        except ValueError:
            print("❌ Неверный ID")
        except Exception as e:
            logger.exception(f"❌ Ошибка удаления аккаунта: {e}")
            print(f"❌ Произошла ошибка: {e}")


## Точка входа в CLI
async def main():
    """Главная функция CLI"""
    cli = AuthCLI()
    
    try:
        await cli.start()
    except KeyboardInterrupt:
        print("\n\n👋 Прервано пользователем")
    except Exception as e:
        logger.exception(f"💥 Критическая ошибка: {e}")
        print(f"\n💥 Произошла критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

