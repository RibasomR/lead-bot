# 🔍 Channel Discovery Module

Модуль автопоиска и рекомендаций Telegram-каналов для мониторинга лидов.

## Быстрый старт

### 1. Настройка конфигурации

Добавьте в `.env`:

```bash
# Ключевые слова для поиска
CHANNEL_SEARCH_KEYWORDS=боты,python,фриланс,разработка,финтех,крипта

# Количество постов для AI-анализа
CHANNEL_POSTS_COUNT=5

# Минимальный AI score
CHANNEL_MIN_SCORE_THRESHOLD=6.0

# Опционально: TGStat API
TGSTAT_API_KEY=your_key_here
```

### 2. Применение миграций

```bash
# В Docker
docker-compose exec admin_bot alembic upgrade head

# Локально
alembic upgrade head
```

### 3. Использование в коде

```python
from shared.channel_discovery import ChannelDiscoveryService, TelegramSearchProvider
from shared.database.engine import get_session

# Создание провайдера
telegram_provider = TelegramSearchProvider(telethon_client)

# Запуск поиска
async with get_session() as session:
    service = ChannelDiscoveryService(telegram_provider, session)
    candidate_ids = await service.discover_channels()
    
    print(f"Найдено {len(candidate_ids)} каналов")
```

### 4. Тестовый запуск

```bash
python scripts/discover_channels_example.py
```

## Компоненты

- **TelegramSearchProvider** — поиск через Telegram API (обязательный)
- **TGStatProvider** — обогащение метриками (опциональный)
- **ChannelDiscoveryService** — основной сервис координации

## Архитектура

```
Telegram Search → Сбор данных → TGStat (опц.) → Сохранение в БД
     ↓                ↓              ↓                  ↓
  Каналы         Название      Метрики          channel_candidates
                 Описание      Статистика              ↓
                 N постов      Категории          AI-анализ (7.2)
```

## База данных

Таблица `channel_candidates`:
- Базовая информация (название, username, описание)
- Метрики (подписчики, посты)
- AI-оценка (score, комментарий, тип заказов)
- Статусы (добавлен/отклонён)

## Документация

Полная документация: [docs/channel-discovery.md](../../docs/channel-discovery.md)

## Следующие шаги

1. **Фаза 7.2** — AI-оценка кандидатов
2. **Фаза 7.3** — UX в Admin Bot
3. **Фаза 7.4** — Тестирование и калибровка

