"""
## Модели базы данных LeadHunter
SQLAlchemy ORM модели для всех таблиц системы.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    BigInteger, String, Text, Integer, Boolean, DateTime, 
    Float, ForeignKey, Index, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


## Базовый класс для всех моделей
class Base(DeclarativeBase):
    """Базовый класс SQLAlchemy для всех моделей"""
    pass


## Enum для типов чатов
class ChatType(str, Enum):
    """Типы Telegram чатов"""
    GROUP = "group"
    CHANNEL = "channel"
    SUPERGROUP = "supergroup"


## Enum для статусов лидов
class LeadStatus(str, Enum):
    """Статусы обработки лидов"""
    NEW = "new"
    VIEWED = "viewed"
    REPLIED = "replied"
    IGNORED = "ignored"


## Enum для стилей общения
class CommunicationStyle(str, Enum):
    """Стили общения для аккаунтов"""
    POLITE = "polite"  # Вежливый/деловой
    FRIENDLY = "friendly"  # Неформальный/дружеский
    AGGRESSIVE = "aggressive"  # Агрессивный/жёсткий


## Модель таблицы accounts
class Account(Base):
    """Telegram-аккаунты для отправки сообщений"""
    
    __tablename__ = "accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, comment="Название аккаунта")
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, comment="Telegram User ID")
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="Номер телефона")
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Telegram username")
    style_default: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=CommunicationStyle.FRIENDLY.value,
        comment="Стиль общения по умолчанию"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="both",
        comment="Роль: monitor (мониторинг чатов), reply (ответы + поиск), both"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="Активен ли аккаунт")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    
    # Relationships
    replies: Mapped[list["Reply"]] = relationship("Reply", back_populates="account")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            f"style_default IN ('{CommunicationStyle.POLITE.value}', '{CommunicationStyle.FRIENDLY.value}', '{CommunicationStyle.AGGRESSIVE.value}')",
            name="check_style_default"
        ),
        Index("idx_accounts_enabled", "enabled"),
        Index("idx_accounts_tg_user_id", "tg_user_id"),
    )
    
    def __repr__(self) -> str:
        return f"<Account(id={self.id}, label='{self.label}', enabled={self.enabled})>"


## Модель таблицы chats
class Chat(Base):
    """Telegram-чаты для мониторинга"""
    
    __tablename__ = "chats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, comment="Telegram Chat ID")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название чата")
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Username чата")
    type: Mapped[str] = mapped_column(String(20), nullable=False, comment="Тип чата")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="Приоритет мониторинга")
    is_whitelisted: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False, 
        comment="В белом списке"
    )
    is_blacklisted: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False, 
        comment="В чёрном списке"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="Активен ли мониторинг")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    
    # Relationships
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="chat")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            f"type IN ('{ChatType.GROUP.value}', '{ChatType.CHANNEL.value}', '{ChatType.SUPERGROUP.value}')",
            name="check_chat_type"
        ),
        CheckConstraint("priority >= 1", name="check_priority_positive"),
        Index("idx_chats_enabled", "enabled"),
        Index("idx_chats_tg_chat_id", "tg_chat_id"),
        Index("idx_chats_priority", "priority"),
    )
    
    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, title='{self.title}', type='{self.type}', enabled={self.enabled})>"


## Модель таблицы leads
class Lead(Base):
    """Найденные лиды в чатах"""
    
    __tablename__ = "leads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="ID сообщения в чате")
    author_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="Telegram User ID автора")
    author_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Username автора")
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Имя автора")
    message_text: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст сообщения")
    message_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="Ссылка на сообщение")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="ru", comment="Язык сообщения")
    stack_tags: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True, 
        comment="Извлечённые технологии через запятую"
    )
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=LeadStatus.NEW.value,
        comment="Статус обработки"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    
    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="leads")
    ai_data: Mapped[Optional["LeadAIData"]] = relationship(
        "LeadAIData", 
        back_populates="lead",
        uselist=False,
        cascade="all, delete-orphan"
    )
    replies: Mapped[list["Reply"]] = relationship("Reply", back_populates="lead")
    
    ## Источник лида: мониторинг чата или глобальный поиск
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="monitor",
        comment="Источник: monitor | search_global"
    )
    ## Черновик автоответа
    draft_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Черновик автоответа")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            f"status IN ('{LeadStatus.NEW.value}', '{LeadStatus.VIEWED.value}', '{LeadStatus.REPLIED.value}', '{LeadStatus.IGNORED.value}')",
            name="check_lead_status"
        ),
        CheckConstraint("language IN ('ru', 'en', 'other')", name="check_language"),
        CheckConstraint("source IN ('monitor', 'search_global')", name="check_lead_source"),
        Index("idx_leads_chat_message", "chat_id", "message_id", unique=True),
        Index("idx_leads_status", "status"),
        Index("idx_leads_created_at", "created_at"),
        Index("idx_leads_author_id", "author_id"),
        Index("idx_leads_source", "source"),
    )
    
    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, chat_id={self.chat_id}, status='{self.status}')>"


## Модель таблицы lead_ai_data
class LeadAIData(Base):
    """Данные анализа лида от ИИ"""
    
    __tablename__ = "lead_ai_data"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("leads.id", ondelete="CASCADE"), 
        nullable=False,
        unique=True
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Краткое описание лида")
    quality_score: Mapped[Optional[float]] = mapped_column(
        Float, 
        nullable=True, 
        comment="Оценка качества (1-5)"
    )
    tone_recommendation: Mapped[Optional[str]] = mapped_column(
        String(20), 
        nullable=True, 
        comment="Рекомендуемый тон"
    )
    price_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Минимальная цена")
    price_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Максимальная цена")
    reply_variants: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True, 
        comment="JSON с вариантами ответов"
    )
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Полный ответ от AI")
    ai_model_used: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Использованная модель"
    )
    ## v2: Данные AI-классификатора
    is_order: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, comment="Классификатор: это заказ?")
    relevance_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Релевантность профилю (1-10)"
    )
    estimated_budget: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Оценка бюджета от AI"
    )
    tags: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON массив тегов/технологий"
    )
    classifier_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Модель классификатора"
    )
    ## v2: Сгенерированный черновик ответа
    generated_reply: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Сгенерированный черновик ответа"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="ai_data")

    # Constraints
    __table_args__ = (
        CheckConstraint("quality_score IS NULL OR (quality_score >= 1 AND quality_score <= 5)", name="check_quality_score"),
        CheckConstraint("relevance_score IS NULL OR (relevance_score >= 1 AND relevance_score <= 10)", name="check_relevance_score"),
        CheckConstraint("price_min IS NULL OR price_min >= 0", name="check_price_min"),
        CheckConstraint("price_max IS NULL OR price_max >= 0", name="check_price_max"),
        Index("idx_lead_ai_data_lead_id", "lead_id"),
        Index("idx_lead_ai_data_quality", "quality_score"),
        Index("idx_lead_ai_data_relevance", "relevance_score"),
        ## Композитный индекс для поиска по качеству и дате
        Index("idx_lead_ai_data_quality_created", "quality_score", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<LeadAIData(id={self.id}, lead_id={self.lead_id}, score={self.quality_score})>"


## Модель таблицы replies
class Reply(Base):
    """Отправленные отклики на лиды"""
    
    __tablename__ = "replies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    style_used: Mapped[str] = mapped_column(String(20), nullable=False, comment="Использованный стиль")
    reply_text: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст отправленного ответа")
    fast_mode_used: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False, 
        comment="Использован ли режим быстрой отправки"
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    was_successful: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=True, 
        comment="Успешна ли отправка"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Ошибка при отправке")
    
    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="replies")
    account: Mapped["Account"] = relationship("Account", back_populates="replies")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            f"style_used IN ('{CommunicationStyle.POLITE.value}', '{CommunicationStyle.FRIENDLY.value}', '{CommunicationStyle.AGGRESSIVE.value}')",
            name="check_style_used"
        ),
        Index("idx_replies_lead_id", "lead_id"),
        Index("idx_replies_account_id", "account_id"),
        Index("idx_replies_sent_at", "sent_at"),
        ## Композитный индекс для антиспам-проверок
        Index("idx_replies_account_sent_success", "account_id", "sent_at", "was_successful"),
    )
    
    def __repr__(self) -> str:
        return f"<Reply(id={self.id}, lead_id={self.lead_id}, account_id={self.account_id}, sent_at={self.sent_at})>"


## Enum для источников поиска каналов
class ChannelSource(str, Enum):
    """Источники данных для автопоиска каналов"""
    TELEGRAM = "telegram"  # Поиск через Telegram API (Telethon)
    TGSTAT = "tgstat"  # Данные из TGStat API


## Модель таблицы channel_candidates для автопоиска каналов
class ChannelCandidate(Base):
    """Кандидаты каналов для автопоиска и AI-оценки"""
    
    __tablename__ = "channel_candidates"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_chat_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, 
        nullable=True, 
        comment="Telegram Chat ID (если известен)"
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(100), 
        nullable=True, 
        comment="Username канала (@channel)"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название канала")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Описание канала")
    invite_link: Mapped[Optional[str]] = mapped_column(
        String(500), 
        nullable=True, 
        comment="Ссылка-приглашение"
    )
    members_count: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True, 
        comment="Количество подписчиков"
    )
    recent_posts: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True, 
        comment="JSON с последними N постами"
    )
    search_query: Mapped[Optional[str]] = mapped_column(
        String(200), 
        nullable=True, 
        comment="Поисковый запрос, по которому найден"
    )
    source: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        comment="Источник данных (telegram/tgstat)"
    )
    ai_score: Mapped[Optional[float]] = mapped_column(
        Float, 
        nullable=True, 
        comment="AI оценка релевантности (0-10)"
    )
    ai_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Комментарий AI")
    ai_order_type: Mapped[Optional[str]] = mapped_column(
        String(100), 
        nullable=True, 
        comment="Тип заказов (фриланс/вакансии/стажировки)"
    )
    is_added_to_monitoring: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False, 
        comment="Добавлен ли в мониторинг"
    )
    is_rejected: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False, 
        comment="Отклонён оператором"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 10)",
            name="check_ai_score"
        ),
        CheckConstraint(
            f"source IN ('{ChannelSource.TELEGRAM.value}', '{ChannelSource.TGSTAT.value}')",
            name="check_source"
        ),
        Index("idx_channel_candidates_username", "username"),
        Index("idx_channel_candidates_tg_chat_id", "tg_chat_id"),
        Index("idx_channel_candidates_ai_score", "ai_score"),
        Index("idx_channel_candidates_added", "is_added_to_monitoring"),
        Index("idx_channel_candidates_source_created", "source", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<ChannelCandidate(id={self.id}, title='{self.title}', score={self.ai_score})>"


## Модель таблицы operator_settings (singleton — одна строка)
class OperatorSettings(Base):
    """Настройки оператора (язык и т.д.)"""

    __tablename__ = "operator_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, comment="Telegram User ID оператора")
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ru",
        comment="Язык интерфейса: ru / en"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_operator_settings_tg_id", "telegram_id"),
    )

    def __repr__(self) -> str:
        return f"<OperatorSettings(id={self.id}, lang='{self.language}')>"


## Модель таблицы freelancer_profile (singleton — одна строка)
class FreelancerProfile(Base):
    """Профиль фрилансера для генерации автоответов"""

    __tablename__ = "freelancer_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stack: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Стек технологий (Python, Node.js, aiogram, Telethon, Next.js, PostgreSQL, Docker, n8n, AI)"
    )
    specialization: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Специализация (Telegram боты, автоматизация, веб, AI-интеграции)"
    )
    preferences: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Предпочтения: что нравится/не нравится"
    )
    min_budget: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Минимальный бюджет проекта (руб)"
    )
    about: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="О себе — текст для генерации автоответов"
    )
    portfolio_url: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Портфолио — описание проектов и ссылки"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<FreelancerProfile(id={self.id}, stack='{self.stack[:30] if self.stack else ''}...')>"


## Модель таблицы search_queries (поисковые фразы для search_global)
class SearchQuery(Base):
    """Поисковые фразы для Telegram Premium search_global"""

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_text: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True,
        comment="Текст поискового запроса"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="Активен ли запрос")
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="Когда последний раз использовался"
    )
    results_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Сколько результатов нашёл"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    results: Mapped[list["SearchGlobalResult"]] = relationship(
        "SearchGlobalResult", back_populates="query", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_search_queries_enabled", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<SearchQuery(id={self.id}, text='{self.query_text}', enabled={self.enabled})>"


## Модель таблицы search_global_results (дедупликация глобального поиска)
class SearchGlobalResult(Base):
    """Результаты глобального поиска для дедупликации"""

    __tablename__ = "search_global_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=False
    )
    chat_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Telegram Chat ID")
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="ID сообщения")
    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Текст сообщения")
    author_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="ID автора")
    found_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    is_processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Обработано ли классификатором"
    )

    # Relationships
    query: Mapped["SearchQuery"] = relationship("SearchQuery", back_populates="results")

    __table_args__ = (
        Index("idx_sgr_chat_message", "chat_tg_id", "message_id", unique=True),
        Index("idx_sgr_query_id", "query_id"),
        Index("idx_sgr_is_processed", "is_processed"),
    )

    def __repr__(self) -> str:
        return f"<SearchGlobalResult(id={self.id}, chat={self.chat_tg_id}, msg={self.message_id})>"
