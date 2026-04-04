# 🎯 LeadHunter — Автоматический поиск лидов в Telegram

Автоматизированная система мониторинга узконишевых IT-чатов для поиска заказов. Вылавливает потенциальные лиды по ключевым словам и подаёт оператору с AI-рекомендациями.

## ✨ Возможности

- 🔍 **Мониторинг 30+ чатов** одновременно через userbot
- 🤖 **AI-помощник** для генерации откликов (OpenRouter)
- 💬 **3 стиля общения**: вежливый, дружеский, жёсткий
- 📊 **Умная оценка** качества лидов и рекомендации по ценам
- 🎛️ **Управление через Telegram** — никаких веб-интерфейсов
- 🔐 **Защита от банов**: антиспам, лимиты активности, задержки
- 📈 **История лидов** с пагинацией и фильтрами
- 🆕 **Автопоиск каналов** — автоматический поиск и рекомендации новых каналов (Фаза 7)

## 🏗️ Архитектура

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

**3 сервиса в Docker:**
1. **Admin Bot** — интерфейс оператора (карточки лидов, команды)
2. **Lead Listener** — мониторинг чатов через 2-5 userbot-аккаунтов
3. **PostgreSQL** — хранилище лидов, чатов, аккаунтов, AI-анализа

## 📋 Требования

- Docker 20.10+
- Docker Compose 2.0+
- 2GB RAM
- Linux VPS (рекомендуется Ubuntu 22.04+)

## 🚀 Быстрый старт

⚡ **За 5 минут**: [QUICKSTART.md](QUICKSTART.md)

```bash
# 1. Клонирование
git clone <your-repo-url> lead-hunter && cd lead-hunter

# 2. Настройка .env
cp env.example .env
nano .env  # Заполни учётные данные (см. ниже)

# 3. Запуск
docker-compose up -d

# 4. Миграции БД
docker-compose exec admin_bot python -m alembic upgrade head

# 5. Авторизация userbot
docker-compose exec lead_listener python auth_cli.py

# 6. Добавь чаты через бота: /add_chat
```

### Учётные данные для `.env`

| Параметр | Где получить |
|----------|--------------|
| `ADMIN_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` |
| `OPERATOR_USER_ID` | [@userinfobot](https://t.me/userinfobot) |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) → API tools |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) → Settings |
| `POSTGRES_PASSWORD` | Придумай сам |

📚 **Документация:**
- [Деплой и настройка](DEPLOYGUIDE.md)
- [Авторизация аккаунтов](ACCOUNT_AUTH.md)
- [Автопоиск каналов](channel-discovery.md) 🆕
- [Устранение проблем](TROUBLESHOOTING.md)

## 📖 Использование

### Основные команды

- `/start` — запуск и главное меню
- `/leads` — история лидов с фильтрами
- `/add_chat` — добавить чат для мониторинга
- `/list_chats` — список отслеживаемых чатов
- `/list_accounts` — список userbot-аккаунтов

### Работа с лидом

1. Бот присылает карточку нового лида с AI-анализом
2. Выбираешь аккаунт и стиль ответа кнопками
3. Отправляешь ответ одним кликом или пишешь свой

## 🛠️ Настройка

### Ключевые слова для поиска

Редактируй в `.env`:
```env
LEAD_KEYWORDS=нужен бот,создать бота,telegram bot,Next.js,автоматизация
```

### Антиспам лимиты

```env
MAX_REPLIES_PER_CHAT_PER_HOUR=5  # Макс. откликов/час на чат
MIN_SEND_DELAY=2                  # Мин. задержка между отправками (сек)
MAX_SEND_DELAY=10                 # Макс. задержка (сек)
```

### AI-модели

```env
AI_MODEL_PRIMARY=meta-llama/llama-3.3-70b-instruct:free    # Основная
AI_MODEL_SECONDARY=qwen/qwen-2.5-72b-instruct:free         # Резервная
```

По умолчанию бесплатные модели. Можешь заменить на платные для лучшего качества.

## 📊 Мониторинг

```bash
# Статус сервисов
docker-compose ps

# Логи
docker-compose logs -f admin_bot
docker-compose logs -f lead_listener

# Подключение к БД
docker-compose exec db psql -U leadhunter -d leadhunter_db
```

## 🐛 Troubleshooting

Полный список проблем и решений: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

**Быстрые решения:**

```bash
# Бот не отвечает
docker-compose logs admin_bot

# Userbot не логинится
rm sessions/*.session && docker-compose restart lead_listener

# Ошибка БД
docker-compose restart db && sleep 10 && docker-compose restart admin_bot lead_listener

# Полный сброс
docker-compose down -v && docker-compose up -d
```

## 📁 Структура проекта

```
lead-hunter/
├── admin_bot/          # Admin Bot (aiogram)
├── lead_listener/      # Lead Listener (Telethon)
├── shared/             # Общие модули (БД, AI)
│   ├── database/       # Модели, CRUD, миграции
│   ├── ai/             # AI Advisor (OpenRouter)
│   └── utils/          # Логирование, обработка ошибок
├── migrations/         # Alembic миграции
├── sessions/           # Сессии userbot (не коммитить!)
├── logs/               # Логи
├── docs/               # Документация
├── config.py           # Конфигурация (Pydantic)
├── docker-compose.yml  # Docker Compose
└── requirements.txt    # Зависимости
```

## 📚 Документация

- [Деплой-гайд](docs/DEPLOYGUIDE.md) — пошаговая настройка
- [Troubleshooting](docs/TROUBLESHOOTING.md) — решение проблем
- [Roadmap](docs/roadmap.md) — план разработки
- [Changelog](docs/CHANGELOG.md) — история изменений

Технические детали:
- [Admin Bot](docs/admin-bot.md)
- [Lead Listener](docs/lead-listener.md)
- [AI Advisor](docs/ai-advisor.md)

## ⚠️ Важные замечания

1. **Безопасность**: Никогда не коммить `.env` и `sessions/`
2. **Лимиты Telegram**: Следи за антиспам-лимитами, иначе бан
3. **Userbot**: Используй только свои аккаунты
4. **Законность**: Соблюдай правила чатов и ToS Telegram

## 📝 Roadmap

- [x] Фаза 0-5: Базовая система (100%)
- [ ] Фаза 6: Финализация MVP
  - [ ] Тестирование полного цикла
  - [ ] Оптимизация и багфиксинг
  - [x] Документация

Полный план: [docs/roadmap.md](docs/roadmap.md)

## 📄 Лицензия

MIT License — делай что хочешь, но на свой риск 😉

---

**⚡ LeadHunter** — разработано для личного использования.  
Используй ответственно и соблюдай правила Telegram.

