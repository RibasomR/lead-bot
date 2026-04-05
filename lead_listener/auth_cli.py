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
        print("🔐 LeadHunter - Telegram Account Authorization")
        print("=" * 60)
        print()

        # Initialize DB
        await init_db()

        while True:
            print("\n📋 Main menu:")
            print("  1. Authorize existing account")
            print("  2. Add new account")
            print("  3. View accounts")
            print("  4. Delete account")
            print("  0. Exit")
            print()

            choice = input("Select action: ").strip()

            if choice == '1':
                await self._auth_existing_account()
            elif choice == '2':
                await self._add_account()
            elif choice == '3':
                await self._list_accounts()
            elif choice == '4':
                await self._remove_account()
            elif choice == '0':
                print("\n👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please try again.")
                
    async def _auth_existing_account(self):
        """Авторизовать существующий аккаунт (уже добавленный через бот)"""
        print("\n" + "=" * 60)
        print("🔑 Authorize Existing Account")
        print("=" * 60)

        ## Show unauthorized accounts (tg_user_id == 0 or disabled)
        async with get_session() as session:
            accounts = await get_all_accounts(session)

        if not accounts:
            print("\n⚠️ No accounts in DB. Add one via bot or option 2.")
            return

        ## Filter unauthorized
        unauthed = [a for a in accounts if a.tg_user_id == 0 or not a.enabled]

        print("\n📋 Accounts requiring authorization:")
        if unauthed:
            for a in unauthed:
                print(f"  🆔 {a.id} | {a.label} | 📞 {a.phone or '?'} | tg_id={a.tg_user_id}")
        else:
            print("  ✅ All accounts are authorized!")
            print("\n📋 All accounts:")
            for a in accounts:
                status = "✅" if a.enabled else "❌"
                print(f"  {status} 🆔 {a.id} | {a.label} | 📞 {a.phone or '?'} | tg_id={a.tg_user_id}")

        account_id = input("\nEnter account ID to authorize (0 to cancel): ").strip()

        try:
            account_id = int(account_id)
        except ValueError:
            print("❌ Invalid ID")
            return

        if account_id == 0:
            print("❌ Cancelled")
            return

        ## Load account
        async with get_session() as session:
            account = await get_account_by_id(session, account_id)

        if not account:
            print(f"❌ Account with ID {account_id} not found")
            return

        phone = account.phone
        if not phone:
            phone = input("📞 Phone not set. Enter phone number (e.g. +79991234567): ").strip()
            if not phone.startswith('+'):
                print("❌ Phone must start with '+'")
                return

        print(f"\n🔄 Authorizing account '{account.label}' ({phone})...")

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
                print("✅ Already authorized!")
                me = await self.client.get_me()
            else:
                print("📨 Sending authorization code...")
                await self.client.send_code_request(phone)

                code = input("📨 Enter code from Telegram: ").strip()

                try:
                    await self.client.sign_in(phone, code)
                    me = await self.client.get_me()
                except SessionPasswordNeededError:
                    password = input("🔒 Enter 2FA password: ").strip()
                    await self.client.sign_in(password=password)
                    me = await self.client.get_me()

            print(f"\n✅ Authorization successful!")
            print(f"   👤 Name: {me.first_name} {me.last_name or ''}")
            print(f"   🆔 Telegram ID: {me.id}")
            print(f"   📝 Username: @{me.username or 'not set'}")

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

            print(f"\n✅ Account '{account.label}' authorized and activated!")
            print(f"   📁 Session: account_{account_id}.session")

        except PhoneNumberInvalidError:
            print("❌ Invalid phone number")
        except PhoneCodeInvalidError:
            print("❌ Invalid authorization code")
        except PhoneCodeExpiredError:
            print("❌ Authorization code expired. Please try again.")
        except FloodWaitError as e:
            print(f"❌ Too many attempts. Wait {e.seconds} seconds.")
        except Exception as e:
            logger.exception(f"❌ Authorization error: {e}")
            print(f"❌ An error occurred: {e}")
        finally:
            if self.client:
                await self.client.disconnect()

    async def _add_account(self):
        """Добавить новый аккаунт через авторизацию"""
        print("\n" + "=" * 60)
        print("📱 Add New Account")
        print("=" * 60)

        # Enter phone number
        phone = input("\nEnter phone number (international format, e.g. +79991234567): ").strip()

        if not phone.startswith('+'):
            print("❌ Phone must start with '+'")
            return

        # Enter account label
        label = input("Enter account name (e.g. 'Work account 1'): ").strip()

        if not label:
            print("❌ Name cannot be empty")
            return

        # Select default communication style
        print("\n📝 Select default communication style:")
        print("  1. Polite/formal (polite)")
        print("  2. Casual/friendly (friendly)")
        print("  3. Assertive/aggressive (aggressive)")

        style_choice = input("Your choice (default 2): ").strip() or '2'
        
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
                print("✅ Account already authorized")
                me = await self.client.get_me()
            else:
                # Request authorization code
                print("\n🔄 Sending authorization code...")
                await self.client.send_code_request(phone)

                code = input("📨 Enter code from Telegram: ").strip()

                try:
                    # Try signing in with code
                    await self.client.sign_in(phone, code)
                    me = await self.client.get_me()

                except SessionPasswordNeededError:
                    # 2FA password required
                    password = input("🔒 Enter 2FA password: ").strip()
                    await self.client.sign_in(password=password)
                    me = await self.client.get_me()

            # Authorization successful
            print(f"\n✅ Authorization successful!")
            print(f"   👤 Name: {me.first_name} {me.last_name or ''}")
            print(f"   🆔 ID: {me.id}")
            print(f"   📝 Username: @{me.username or 'not set'}")
            
            # Сохранение в БД
            async with get_session() as session:
                # Проверяем, не существует ли уже
                existing = await get_account_by_tg_id(session, me.id)
                
                if existing:
                    print(f"\n⚠️ Account with ID {me.id} already exists in DB (label: '{existing.label}')")
                    overwrite = input("Overwrite? (y/n): ").strip().lower()

                    if overwrite != 'y':
                        print("❌ Cancelled")
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
                
                print(f"\n✅ Account '{label}' successfully added!")
                print(f"   🆔 DB ID: {account.id}")
                print(f"   📱 Telegram ID: {account.tg_user_id}")
                print(f"   🎨 Style: {account.style_default}")

        except PhoneNumberInvalidError:
            print("❌ Invalid phone number")
        except PhoneCodeInvalidError:
            print("❌ Invalid authorization code")
        except PhoneCodeExpiredError:
            print("❌ Authorization code expired. Please try again.")
        except FloodWaitError as e:
            print(f"❌ Too many attempts. Wait {e.seconds} seconds.")
        except Exception as e:
            logger.exception(f"❌ Authorization error: {e}")
            print(f"❌ An error occurred: {e}")
        finally:
            if self.client:
                await self.client.disconnect()
                
    async def _list_accounts(self):
        """Показать список всех аккаунтов"""
        print("\n" + "=" * 60)
        print("📋 Account List")
        print("=" * 60)

        async with get_session() as session:
            accounts = await get_all_accounts(session)

            if not accounts:
                print("\n⚠️ No registered accounts")
                return

            for account in accounts:
                status = "✅ Active" if account.enabled else "❌ Disabled"
                print(f"\n🆔 ID: {account.id}")
                print(f"   📛 Name: {account.label}")
                print(f"   📱 Telegram ID: {account.tg_user_id}")
                print(f"   👤 Username: @{account.username or 'not set'}")
                print(f"   📞 Phone: {account.phone or 'not set'}")
                print(f"   🎨 Style: {account.style_default}")
                print(f"   📊 Status: {status}")
                print(f"   📅 Created: {account.created_at.strftime('%d.%m.%Y %H:%M')}")
                
    async def _remove_account(self):
        """Удалить аккаунт"""
        print("\n" + "=" * 60)
        print("🗑️ Delete Account")
        print("=" * 60)

        # Show list
        await self._list_accounts()

        account_id = input("\nEnter account ID to delete (0 to cancel): ").strip()

        try:
            account_id = int(account_id)

            if account_id == 0:
                print("❌ Cancelled")
                return

            async with get_session() as session:
                from shared.database.crud import get_account_by_id, delete_account

                account = await get_account_by_id(session, account_id)

                if not account:
                    print(f"❌ Account with ID {account_id} not found")
                    return

                confirm = input(f"⚠️ Delete account '{account.label}'? (yes/no): ").strip().lower()

                if confirm != 'yes':
                    print("❌ Cancelled")
                    return

                # Delete from DB
                await delete_account(session, account_id)
                await session.commit()

                # Delete session file
                session_file = settings.sessions_dir / f"session_{account.tg_user_id}.session"
                if session_file.exists():
                    session_file.unlink()

                print(f"✅ Account '{account.label}' successfully deleted")

        except ValueError:
            print("❌ Invalid ID")
        except Exception as e:
            logger.exception(f"❌ Account deletion error: {e}")
            print(f"❌ An error occurred: {e}")


## Точка входа в CLI
async def main():
    """Главная функция CLI"""
    cli = AuthCLI()
    
    try:
        await cli.start()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
    except Exception as e:
        logger.exception(f"💥 Critical error: {e}")
        print(f"\n💥 Critical error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

