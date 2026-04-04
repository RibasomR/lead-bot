# 🚀 Деплой LeadHunter

## Быстрый старт (5 минут)

### 1. Подготовка окружения

```bash
# Клонирование
git clone <your-repo-url> lead-hunter
cd lead-hunter

# Настройка .env
cp env.example .env
nano .env
```

### 2. Получение учётных данных

| Параметр | Где получить | Инструкция |
|----------|--------------|------------|
| `ADMIN_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | `/newbot` → копируй токен |
| `OPERATOR_USER_ID` | [@userinfobot](https://t.me/userinfobot) | Отправь `/start` |
| `TELEGRAM_API_ID`<br>`TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) | API development tools → Create app |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) | Settings → API Keys |
| `POSTGRES_PASSWORD` | Сам придумай | Надёжный пароль |

### 3. Запуск

```bash
# Сборка и запуск
docker compose up -d

# Проверка статуса
docker compose ps

# Применение миграций БД
docker compose exec admin_bot python -m alembic upgrade head
```

### 4. Добавление и авторизация аккаунтов

**Шаг 4.1:** Добавь аккаунты через Admin Bot:
- Открой бота в Telegram
- `/start` → **👤 Аккаунты** → **➕ Добавить аккаунт**
- Введи название, номер телефона, выбери стиль

**Шаг 4.2:** Авторизуй аккаунты в Lead Listener:
```bash
docker compose exec -it lead_listener python lead_listener/auth_cli.py
```

⚠️ **Важно:** Флаг `-it` обязателен для интерактивного ввода!

Введи ID аккаунта → код из Telegram → 2FA пароль (если есть).

📖 **Подробная инструкция:** [ACCOUNT_AUTH.md](ACCOUNT_AUTH.md)

### 5. Добавление чатов

Открой бота в Telegram:
- `/start` — запуск
- `/add_chat` — переслать сообщение из чата для мониторинга

---

## Проверка работы

```bash
# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f admin_bot
docker compose logs -f lead_listener

# Статус БД
docker compose exec db psql -U leadhunter -d leadhunter_db -c "SELECT COUNT(*) FROM leads;"
```

---

## Команды бота

- `/start` — главное меню
- `/leads` — история лидов
- `/add_chat` — добавить чат
- `/list_chats` — список чатов
- `/list_accounts` — список аккаунтов
- `/enable_chat <id>` / `/disable_chat <id>` — вкл/выкл чат

---

## Настройка фильтров

Отредактируй в `.env`:

```env
# Ключевые слова (через запятую)
LEAD_KEYWORDS=нужен бот,создать бота,telegram bot,автоматизация,Next.js

# Антиспам
MAX_REPLIES_PER_CHAT_PER_HOUR=5
MIN_SEND_DELAY=2
MAX_SEND_DELAY=10
```

---

## Обновление

```bash
git pull
docker compose down
docker compose up -d --build
docker compose exec admin_bot python -m alembic upgrade head
docker compose logs -f

```

---

## Backup

```bash
# Создать бэкап БД
docker compose exec db pg_dump -U leadhunter leadhunter_db > backup_$(date +%Y%m%d).sql

# Восстановить
docker compose exec -T db psql -U leadhunter -d leadhunter_db < backup_20241115.sql
```

---

