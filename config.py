"""
## Модуль конфигурации LeadHunter
Загружает и валидирует все переменные окружения при старте приложения.
Использует pydantic-settings для строгой типизации и валидации.
"""

from typing import Optional, List
from pathlib import Path

from pydantic import Field, field_validator, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


## Базовый класс настроек приложения
class Settings(BaseSettings):
    """
    Центральный класс конфигурации для всех сервисов LeadHunter.
    Автоматически загружает переменные из .env файла и валидирует их.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # === Admin Bot Configuration ===
    admin_bot_token: str = Field(
        ...,
        description="Токен Telegram бота от @BotFather"
    )
    
    operator_user_id: int = Field(
        ...,
        description="Telegram ID оператора (единственный пользователь бота)"
    )
    
    # === Database Configuration ===
    database_url: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection string"
    )
    
    postgres_user: str = Field(
        default="leadhunter",
        description="PostgreSQL username"
    )
    
    postgres_password: str = Field(
        ...,
        description="PostgreSQL password"
    )
    
    postgres_db: str = Field(
        default="leadhunter_db",
        description="PostgreSQL database name"
    )
    
    # === Telegram API Configuration ===
    telegram_api_id: int = Field(
        ...,
        description="Telegram API ID from my.telegram.org"
    )
    
    telegram_api_hash: str = Field(
        ...,
        description="Telegram API Hash from my.telegram.org"
    )
    
    # === OpenRouter AI Configuration ===
    openrouter_api_key: str = Field(
        ...,
        description="OpenRouter API key"
    )

    ai_model_primary: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free",
        description="Основная AI модель (OpenRouter)"
    )

    ai_model_secondary: str = Field(
        default="qwen/qwen-2.5-72b-instruct:free",
        description="Запасная AI модель (OpenRouter)"
    )
    
    ai_request_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Таймаут AI запросов в секундах"
    )
    
    # === Lead Listener Configuration ===
    max_replies_per_chat_per_hour: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Максимум откликов в час на один чат"
    )
    
    min_send_delay: int = Field(
        default=2,
        ge=0,
        le=60,
        description="Минимальная задержка между отправками (секунды)"
    )
    
    max_send_delay: int = Field(
        default=10,
        ge=0,
        le=300,
        description="Максимальная задержка между отправками (секунды)"
    )
    
    admin_bot_api_url: Optional[str] = Field(
        default="http://admin_bot:8000",
        description="URL Admin Bot API для отправки уведомлений"
    )
    
    lead_listener_api_port: Optional[int] = Field(
        default=8001,
        description="Порт Lead Listener API"
    )
    
    # === Logging Configuration ===
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования"
    )
    
    log_file: Path = Field(
        default=Path("logs/leadhunter.log"),
        description="Путь к файлу логов"
    )
    
    # === v2: AI Classifier (DeepSeek) ===
    deepseek_model: str = Field(
        default="deepseek/deepseek-chat-v3-0324",
        description="Модель DeepSeek для AI-классификации заказов"
    )

    classification_threshold: float = Field(
        default=5.0,
        ge=1.0,
        le=10.0,
        description="Минимальный порог relevance для мониторинга (1-10)"
    )

    search_classification_threshold: float = Field(
        default=4.0,
        ge=1.0,
        le=10.0,
        description="Порог relevance для глобального поиска (ниже чем мониторинг)"
    )

    # === v2: Reply Generator ===
    reply_model: str = Field(
        default="deepseek/deepseek-chat-v3-0324",
        description="Модель для генерации ответов на лиды"
    )

    reply_api_base: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL API для генерации ответов (OpenRouter или Antigravity proxy)"
    )

    reply_api_key: Optional[str] = Field(
        default=None,
        description="API ключ для reply API (если None — используется openrouter_api_key)"
    )

    # === v2: Одобренные чаты для мониторинга ===
    default_monitor_chats: str = Field(
        default=(
            "@vibecoderchat,@vibe_coding_community,@vibecoding_community,"
            "@ai_n8n_hub,@botfatherdev,@botoid,@python_scripts,@devschat,"
            "@rupython,@borodutcher,@TgBotDevs,@n8n_ru,@tproger_chat,"
            "@aimarkethubgroup"
        ),
        description="Одобренные чаты для мониторинга (v2)"
    )

    # === DEPRECATED: Keywords (v1, заменяется AI-классификатором) ===
    lead_keywords: str = Field(
        default=(
            "нужен бот,создать бота,телеграм бот,telegram bot,"
            "бот на python,бот для бизнеса,автоматизация,интеграция,"
            "Next.js,сайт на Next,крипта,биржа,трейдинг бот,crypto bot"
        ),
        description="[DEPRECATED v2] Ключевые слова для фильтрации лидов"
    )

    # === DEPRECATED: Channel Discovery (v1, заменяется search_global) ===
    channel_search_keywords: str = Field(
        default=(
            "боты,telegram bot,python,фриланс,freelance,"
            "разработка,development,финтех,fintech,крипта,crypto,"
            "автоматизация,automation,заказы,orders,"
            "it проекты,веб-разработка,backend,frontend,Next.js,React,"
            "программирование,coding,разработчик,developer,заказ разработки,"
            "вайб кодинг,it сообщество,dev чат,программисты чат,"
            "биржа труда,freelance chat,dev community,кодеры"
        ),
        description="[DEPRECATED v2] Ключевые слова для поиска каналов"
    )

    channel_posts_count: int = Field(
        default=5,
        ge=1,
        le=20,
        description="[DEPRECATED v2] Постов для анализа AI"
    )

    channel_min_score_threshold: float = Field(
        default=6.0,
        ge=0.0,
        le=10.0,
        description="[DEPRECATED v2] Минимальный AI score канала"
    )

    tgstat_api_key: Optional[str] = Field(
        default=None,
        description="[DEPRECATED v2] TGStat API ключ"
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Валидация уровня логирования"""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed_levels:
            raise ValueError(
                f"log_level должен быть одним из {allowed_levels}, получено: {v}"
            )
        return v_upper
    
    @field_validator("min_send_delay", "max_send_delay")
    @classmethod
    def validate_send_delays(cls, v: int) -> int:
        """Валидация задержек отправки"""
        if v < 0:
            raise ValueError("Задержка не может быть отрицательной")
        return v
    
    @property
    def default_monitor_chats_list(self) -> List[str]:
        """Возвращает список одобренных чатов для мониторинга (v2)"""
        return [
            chat.strip()
            for chat in self.default_monitor_chats.split(",")
            if chat.strip()
        ]

    @property
    def keywords_list(self) -> List[str]:
        """[DEPRECATED] Возвращает список ключевых слов для фильтрации лидов (lowercase)"""
        return [
            keyword.strip().lower() 
            for keyword in self.lead_keywords.split(",")
            if keyword.strip()
        ]
    
    @property
    def channel_search_keywords_list(self) -> List[str]:
        """Возвращает список ключевых слов для поиска каналов (lowercase)"""
        return [
            keyword.strip().lower() 
            for keyword in self.channel_search_keywords.split(",")
            if keyword.strip()
        ]
    
    @property
    def sessions_dir(self) -> Path:
        """Путь к директории с сессиями userbot"""
        ## Используем абсолютный путь относительно текущей директории (в Docker это /app)
        path = Path("sessions").resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def logs_dir(self) -> Path:
        """Путь к директории с логами"""
        path = self.log_file.parent
        path.mkdir(exist_ok=True, parents=True)
        return path


## Создание экземпляра настроек (синглтон)
def get_settings() -> Settings:
    """
    Возвращает экземпляр настроек приложения.
    При первом вызове загружает и валидирует переменные окружения.
    """
    return Settings()


## Проверка конфигурации при импорте
def validate_config() -> None:
    """
    Проверяет корректность конфигурации при старте приложения.
    Выбрасывает исключение, если конфигурация невалидна.
    """
    try:
        settings = get_settings()
        
        # Проверяем критичные параметры
        assert settings.admin_bot_token, "ADMIN_BOT_TOKEN не установлен"
        assert settings.operator_user_id > 0, "OPERATOR_USER_ID должен быть положительным числом"
        assert settings.telegram_api_id > 0, "TELEGRAM_API_ID должен быть положительным числом"
        assert settings.telegram_api_hash, "TELEGRAM_API_HASH не установлен"
        assert settings.openrouter_api_key, "OPENROUTER_API_KEY не установлен"
        assert settings.postgres_password, "POSTGRES_PASSWORD не установлен"
        
        # Проверяем логику задержек
        if settings.min_send_delay > settings.max_send_delay:
            raise ValueError(
                f"MIN_SEND_DELAY ({settings.min_send_delay}) не может быть больше "
                f"MAX_SEND_DELAY ({settings.max_send_delay})"
            )
        
        print("✅ Конфигурация успешно загружена и валидирована")
        
    except Exception as e:
        print(f"❌ Ошибка валидации конфигурации: {e}")
        raise


## Для удобства экспортируем settings как модуль
settings = get_settings()


if __name__ == "__main__":
    # Запуск валидации при прямом вызове модуля
    validate_config()
    
    # Выводим основные параметры (без секретов)
    print("\n📋 Текущие настройки:")
    print(f"  • Operator ID: {settings.operator_user_id}")
    print(f"  • Database: {settings.postgres_db}")
    print(f"  • AI Model: {settings.deepseek_model}")
    print(f"  • Log Level: {settings.log_level}")
    print(f"  • Monitor chats: {len(settings.default_monitor_chats_list)} шт.")
    print(f"  • Max replies/hour: {settings.max_replies_per_chat_per_hour}")

