<p align="center">
  <h1 align="center">LeadHunter</h1>
  <p align="center">
    <strong>Automated Telegram lead monitoring system with AI-powered analysis</strong>
  </p>
  <p align="center">
    <a href="#features">Features</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#configuration">Configuration</a> •
    <a href="#license">License</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white&style=for-the-badge" alt="Python">
    <img src="https://img.shields.io/badge/Telegram-Bot%20%2B%20Userbot-blue?logo=telegram&logoColor=white&style=for-the-badge" alt="Telegram">
    <img src="https://img.shields.io/badge/AI-OpenRouter-purple?logo=openai&logoColor=white&style=for-the-badge" alt="AI">
    <img src="https://img.shields.io/badge/Docker-Ready-blue?logo=docker&logoColor=white&style=for-the-badge" alt="Docker">
    <img src="https://img.shields.io/github/license/RibasomR/lead-bot?style=for-the-badge" alt="License">
  </p>
</p>

---

LeadHunter monitors 30+ Telegram chats in real-time, catches potential freelance orders and project requests, and delivers them as rich lead cards with AI recommendations — all managed through a Telegram bot interface.

> **🇷🇺 Русская версия:** [docs/README.md](docs/README.md)

## Features

- **Real-time monitoring** — scans 30+ chats simultaneously via Telethon userbot
- **AI-powered analysis** — auto-classifies leads, scores quality (1–5), suggests price ranges
- **Smart replies** — generates context-aware responses in 3 styles (polite, friendly, aggressive)
- **Lead cards** — rich formatted cards with chat, author, stack tags, AI summary
- **Anti-ban protection** — rate limiting, random delays, per-chat hourly limits
- **Channel discovery** — automatically finds and recommends new relevant channels
- **Lead history** — full history with pagination and time-based filters
- **Zero web UI** — everything managed through Telegram commands

## Architecture

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

| Service | Role | Tech |
|---------|------|------|
| **Admin Bot** | Operator interface — lead cards, commands, reply management | aiogram 3.x |
| **Lead Listener** | Chat monitoring via 2–5 userbot accounts | Telethon |
| **PostgreSQL** | Leads, chats, accounts, AI analysis storage | SQLAlchemy + Alembic |
| **AI Advisor** | Lead scoring, reply generation, channel evaluation | OpenRouter API |

## Quick Start

### Prerequisites

- Docker 20.10+ & Docker Compose 2.0+
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Telegram API credentials ([my.telegram.org](https://my.telegram.org))
- OpenRouter API key ([openrouter.ai](https://openrouter.ai))

### Setup

```bash
# Clone
git clone https://github.com/RibasomR/lead-bot.git && cd lead-bot

# Configure
cp .env.example .env
nano .env  # Fill in your credentials

# Launch
docker compose up -d

# Run database migrations
docker compose exec admin_bot python -m alembic upgrade head

# Authorize userbot accounts
docker compose exec -it lead_listener python lead_listener/auth_cli.py
```

Send `/start` to your bot — you're live.

## Configuration

All settings are in `.env`. Key parameters:

| Variable | Description |
|----------|-------------|
| `ADMIN_BOT_TOKEN` | Telegram bot token from @BotFather |
| `OPERATOR_USER_ID` | Your Telegram user ID |
| `TELEGRAM_API_ID` / `API_HASH` | From my.telegram.org |
| `OPENROUTER_API_KEY` | AI API key |
| `DATABASE_URL` | PostgreSQL connection string |
| `MAX_REPLIES_PER_CHAT_PER_HOUR` | Anti-spam rate limit (default: 5) |
| `DEFAULT_MONITOR_CHATS` | Comma-separated chat usernames to monitor |

See [.env.example](.env.example) for the full list.

## How It Works

1. **Lead Listener** joins target chats via userbot accounts
2. Incoming messages are filtered by keywords (configurable)
3. Matched messages are saved as leads, then AI analyzes quality and generates a summary
4. **Admin Bot** sends a lead card to the operator with:
   - Chat name, author, link to original message
   - AI quality score (1–5 stars), suggested price range
   - Stack tags extracted from text
5. Operator chooses an account + reply style, AI generates response options
6. Operator approves or edits the reply, which is sent with anti-ban delays

**Reply styles:**

| Style | Use case |
|-------|----------|
| 🎩 Polite | Corporate clients, formal tone |
| 😊 Friendly | Startups, personal projects |
| 💪 Aggressive | Urgency-driven, price negotiation |

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/leads` | Lead history with filters |
| `/add_chat` | Add chat to monitor (by ID, username, or forward) |
| `/list_chats` | Manage monitored chats |
| `/add_account` | Add userbot account |
| `/list_accounts` | Manage accounts |

## Project Structure

```
lead-bot/
├── admin_bot/          # Telegram bot for operator (aiogram 3.x)
│   ├── handlers/       # Command handlers
│   ├── main.py         # Entry point
│   └── keyboards.py    # Inline & reply keyboards
├── lead_listener/      # Chat monitoring service (Telethon)
│   ├── main.py         # Entry point + HTTP API
│   ├── filters.py      # Keyword matching
│   ├── notifier.py     # Lead delivery to Admin Bot
│   └── rate_limiter.py # Anti-spam protection
├── shared/             # Shared modules
│   ├── ai/             # AI Advisor (OpenRouter)
│   ├── database/       # SQLAlchemy models, CRUD, migrations
│   ├── channel_discovery/  # Auto-discovery of new channels
│   └── utils/          # Logging, error handling
├── migrations/         # Alembic database migrations
├── docker-compose.yml
└── requirements.txt
```

## Tech Stack

- **Python 3.10+** with async/await
- **aiogram 3.x** — Telegram Bot API
- **Telethon** — Telegram Client API (userbot)
- **PostgreSQL** via SQLAlchemy 2.0 + asyncpg
- **Alembic** — database migrations
- **OpenRouter** — AI models (Llama, DeepSeek, Gemini)
- **Docker Compose** — deployment

## License

This project is licensed under the [MIT License](LICENSE).
