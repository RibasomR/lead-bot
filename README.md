<h1 align="center">🎯 LeadHunter — Мониторинг лидов в Telegram</h1>

<p align="center">
  <strong>Ловит заказы из 30+ чатов раньше всех остальных.</strong><br>
  AI классифицирует лиды, оценивает качество и пишет отклики — тебе остаётся нажать «Отправить».
</p>

<p align="center">
  <a href="#как-это-работает">Как это работает</a> •
  <a href="#возможности">Возможности</a> •
  <a href="#архитектура">Архитектура</a> •
  <a href="#быстрый-старт">Быстрый старт</a> •
  <a href="#лицензия">Лицензия</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white&style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/Telegram-Bot%20%2B%20Userbot-blue?logo=telegram&logoColor=white&style=for-the-badge" alt="Telegram">
  <img src="https://img.shields.io/badge/AI-OpenRouter-purple?logo=openai&logoColor=white&style=for-the-badge" alt="AI">
  <img src="https://img.shields.io/badge/Docker-Ready-blue?logo=docker&logoColor=white&style=for-the-badge" alt="Docker">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
</p>

---

Ты фрилансер-разработчик. Каждый день в десятках Telegram-чатов появляются сообщения — _«нужен бот»_, _«ищу разработчика»_, _«кто может автоматизировать?»_. Сидеть в 30 чатах и обновлять ленту весь день невозможно. **LeadHunter делает это за тебя.**

Система мониторит целевые чаты 24/7 через userbot-аккаунты, ловит сообщения по ключевым словам и присылает тебе аккуратную карточку: кто пишет, что хочет, оценка качества от AI и рекомендуемая вилка цен. Выбираешь стиль ответа, корректируешь если нужно, нажимаешь «Отправить» — всё, не выходя из Telegram.

Без веб-дашбордов. Без CRM. Только Telegram и VPS.

## Как это работает

Кто-то пишет в мониторимом чате _«Нужен Telegram-бот для бизнеса, бюджет $500»_ — и через секунду ты получаешь:

```
💬 Чат: @freelance_orders
👤 Автор: @potential_client
📝 «Нужен Telegram-бот для бизнеса, бюджет $500»

🤖 AI-анализ:
   ⭐⭐⭐⭐ Качество: 4/5
   💰 Вилка цен: $400–$800
   🏷️ Стек: Telegram, Bot, aiogram
   🎯 Рекомендация: ответить в дружелюбном тоне, подчеркнуть опыт
```

Бот присылает эту карточку с кнопками действий. Выбираешь стиль ответа, AI генерирует текст, подправляешь и отправляешь. Отклик уходит с рабочего аккаунта с естественными задержками, чтобы не попасть в бан.

## Возможности

- **Мониторинг в реальном времени** — сканирует 30+ чатов одновременно через Telethon userbot
- **AI-анализ** — автоматически классифицирует лиды, оценивает качество (1–5), предлагает вилку цен
- **Умные отклики** — генерирует контекстные ответы в разных стилях
- **Лид-карточки** — форматированные карточки с чатом, автором, стек-тегами, AI-саммари
- **Антибан-защита** — rate limiting, случайные задержки, лимиты откликов на чат в час
- **Автопоиск каналов** — находит и рекомендует новые релевантные каналы
- **История лидов** — полная история с пагинацией и фильтрами по времени
- **Zero web UI** — всё управление через команды Telegram

## Архитектура

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Admin Bot   │────▶│  PostgreSQL  │◀────│Lead Listener │
│  (aiogram)   │     │              │     │  (Telethon)  │
└──────────────┘     └──────────────┘     └──────────────┘
       │                                          │
       └──────────────────┬───────────────────────┘
                          │
                   ┌──────▼──────┐
                   │ AI Advisor  │
                   │ (OpenRouter)│
                   └─────────────┘
```

| Сервис | Роль | Технология |
|--------|------|------------|
| **Admin Bot** | Интерфейс оператора — карточки лидов, команды, управление откликами | aiogram 3.x |
| **Lead Listener** | Мониторинг чатов через 2–5 userbot-аккаунтов | Telethon |
| **PostgreSQL** | Хранилище лидов, чатов, аккаунтов, AI-анализов | SQLAlchemy + Alembic |
| **AI Advisor** | Скоринг лидов, генерация откликов, оценка каналов | OpenRouter API |

## Быстрый старт

### Что нужно

- Docker 20.10+ и Docker Compose 2.0+
- Токен Telegram-бота ([@BotFather](https://t.me/BotFather))
- Telegram API credentials ([my.telegram.org](https://my.telegram.org))
- OpenRouter API key ([openrouter.ai](https://openrouter.ai))

### Установка

```bash
# Клонируем
git clone https://github.com/RibasomR/lead-bot.git && cd lead-bot

# Настраиваем
cp .env.example .env
nano .env  # Заполни свои credentials

# Запускаем
docker compose up -d

# Миграции БД
docker compose exec admin_bot python -m alembic upgrade head

# Авторизуем userbot-аккаунты
docker compose exec -it lead_listener python lead_listener/auth_cli.py
```

Отправь `/start` своему боту — готово.

## Настройка

Все параметры в `.env`. Ключевые:

| Переменная | Описание |
|------------|----------|
| `ADMIN_BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `OPERATOR_USER_ID` | Твой Telegram user ID |
| `TELEGRAM_API_ID` / `API_HASH` | С my.telegram.org |
| `OPENROUTER_API_KEY` | API-ключ для AI |
| `DATABASE_URL` | Строка подключения к PostgreSQL |
| `MAX_REPLIES_PER_CHAT_PER_HOUR` | Антиспам-лимит откликов (по умолчанию: 5) |
| `DEFAULT_MONITOR_CHATS` | Юзернеймы чатов для мониторинга через запятую |

Полный список — в [.env.example](.env.example).

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/leads` | История лидов с фильтрами |
| `/add_chat` | Добавить чат (по ID, username или пересылкой) |
| `/list_chats` | Управление чатами |
| `/add_account` | Добавить userbot-аккаунт |
| `/list_accounts` | Управление аккаунтами |

## Структура проекта

```
lead-bot/
├── admin_bot/          # Telegram-бот оператора (aiogram 3.x)
│   ├── handlers/       # Обработчики команд
│   ├── main.py         # Точка входа
│   └── keyboards.py    # Inline и reply клавиатуры
├── lead_listener/      # Сервис мониторинга чатов (Telethon)
│   ├── main.py         # Точка входа + HTTP API
│   ├── filters.py      # Фильтрация по ключевым словам
│   ├── notifier.py     # Доставка лидов в Admin Bot
│   └── rate_limiter.py # Антиспам-защита
├── shared/             # Общие модули
│   ├── ai/             # AI Advisor (OpenRouter)
│   ├── database/       # SQLAlchemy модели, CRUD, миграции
│   ├── channel_discovery/  # Автопоиск каналов
│   └── utils/          # Логирование, обработка ошибок
├── migrations/         # Alembic-миграции
├── docker-compose.yml
└── requirements.txt
```

## Стек

- **Python 3.10+** с async/await
- **aiogram 3.x** — Telegram Bot API
- **Telethon** — Telegram Client API (userbot)
- **PostgreSQL** через SQLAlchemy 2.0 + asyncpg
- **Alembic** — миграции БД
- **OpenRouter** — AI-модели (Llama, DeepSeek, Gemini)
- **Docker Compose** — деплой

## Лицензия

[MIT](LICENSE) — делай что хочешь.
