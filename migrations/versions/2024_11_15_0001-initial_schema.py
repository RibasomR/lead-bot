"""Initial database schema

Revision ID: 2024_11_15_0001
Revises: 
Create Date: 2024-11-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2024_11_15_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ## Создание таблицы accounts
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False, comment='Название аккаунта'),
        sa.Column('tg_user_id', sa.BigInteger(), nullable=False, comment='Telegram User ID'),
        sa.Column('phone', sa.String(length=20), nullable=True, comment='Номер телефона'),
        sa.Column('username', sa.String(length=100), nullable=True, comment='Telegram username'),
        sa.Column('style_default', sa.String(length=20), nullable=False, comment='Стиль общения по умолчанию'),
        sa.Column('enabled', sa.Boolean(), nullable=False, comment='Активен ли аккаунт'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("style_default IN ('polite', 'friendly', 'aggressive')", name='check_style_default'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('label'),
        sa.UniqueConstraint('tg_user_id')
    )
    op.create_index('idx_accounts_enabled', 'accounts', ['enabled'])
    op.create_index('idx_accounts_tg_user_id', 'accounts', ['tg_user_id'])

    ## Создание таблицы chats
    op.create_table(
        'chats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tg_chat_id', sa.BigInteger(), nullable=False, comment='Telegram Chat ID'),
        sa.Column('title', sa.String(length=255), nullable=False, comment='Название чата'),
        sa.Column('username', sa.String(length=100), nullable=True, comment='Username чата'),
        sa.Column('type', sa.String(length=20), nullable=False, comment='Тип чата'),
        sa.Column('priority', sa.Integer(), nullable=False, comment='Приоритет мониторинга'),
        sa.Column('is_whitelisted', sa.Boolean(), nullable=False, comment='В белом списке'),
        sa.Column('is_blacklisted', sa.Boolean(), nullable=False, comment='В чёрном списке'),
        sa.Column('enabled', sa.Boolean(), nullable=False, comment='Активен ли мониторинг'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("type IN ('group', 'channel', 'supergroup')", name='check_chat_type'),
        sa.CheckConstraint('priority >= 1', name='check_priority_positive'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tg_chat_id')
    )
    op.create_index('idx_chats_enabled', 'chats', ['enabled'])
    op.create_index('idx_chats_tg_chat_id', 'chats', ['tg_chat_id'])
    op.create_index('idx_chats_priority', 'chats', ['priority'])

    ## Создание таблицы leads
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False, comment='ID сообщения в чате'),
        sa.Column('author_id', sa.BigInteger(), nullable=True, comment='Telegram User ID автора'),
        sa.Column('author_username', sa.String(length=100), nullable=True, comment='Username автора'),
        sa.Column('author_name', sa.String(length=255), nullable=True, comment='Имя автора'),
        sa.Column('message_text', sa.Text(), nullable=False, comment='Текст сообщения'),
        sa.Column('message_url', sa.String(length=500), nullable=True, comment='Ссылка на сообщение'),
        sa.Column('language', sa.String(length=10), nullable=False, comment='Язык сообщения'),
        sa.Column('stack_tags', sa.Text(), nullable=True, comment='Извлечённые технологии через запятую'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='Статус обработки'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('new', 'viewed', 'replied', 'ignored')", name='check_lead_status'),
        sa.CheckConstraint("language IN ('ru', 'en', 'other')", name='check_language'),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_leads_chat_message', 'leads', ['chat_id', 'message_id'], unique=True)
    op.create_index('idx_leads_status', 'leads', ['status'])
    op.create_index('idx_leads_created_at', 'leads', ['created_at'])
    op.create_index('idx_leads_author_id', 'leads', ['author_id'])

    ## Создание таблицы lead_ai_data
    op.create_table(
        'lead_ai_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True, comment='Краткое описание лида'),
        sa.Column('quality_score', sa.Float(), nullable=True, comment='Оценка качества (1-5)'),
        sa.Column('tone_recommendation', sa.String(length=20), nullable=True, comment='Рекомендуемый тон'),
        sa.Column('price_min', sa.Float(), nullable=True, comment='Минимальная цена'),
        sa.Column('price_max', sa.Float(), nullable=True, comment='Максимальная цена'),
        sa.Column('reply_variants', sa.Text(), nullable=True, comment='JSON с вариантами ответов'),
        sa.Column('raw_response', sa.Text(), nullable=True, comment='Полный ответ от AI'),
        sa.Column('ai_model_used', sa.String(length=100), nullable=True, comment='Использованная модель'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('quality_score IS NULL OR (quality_score >= 1 AND quality_score <= 5)', name='check_quality_score'),
        sa.CheckConstraint('price_min IS NULL OR price_min >= 0', name='check_price_min'),
        sa.CheckConstraint('price_max IS NULL OR price_max >= 0', name='check_price_max'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lead_id')
    )
    op.create_index('idx_lead_ai_data_lead_id', 'lead_ai_data', ['lead_id'])
    op.create_index('idx_lead_ai_data_quality', 'lead_ai_data', ['quality_score'])

    ## Создание таблицы replies
    op.create_table(
        'replies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('style_used', sa.String(length=20), nullable=False, comment='Использованный стиль'),
        sa.Column('reply_text', sa.Text(), nullable=False, comment='Текст отправленного ответа'),
        sa.Column('fast_mode_used', sa.Boolean(), nullable=False, comment='Использован ли режим быстрой отправки'),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('was_successful', sa.Boolean(), nullable=False, comment='Успешна ли отправка'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Ошибка при отправке'),
        sa.CheckConstraint("style_used IN ('polite', 'friendly', 'aggressive')", name='check_style_used'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_replies_lead_id', 'replies', ['lead_id'])
    op.create_index('idx_replies_account_id', 'replies', ['account_id'])
    op.create_index('idx_replies_sent_at', 'replies', ['sent_at'])


def downgrade() -> None:
    ## Удаление всех таблиц в обратном порядке
    op.drop_index('idx_replies_sent_at', table_name='replies')
    op.drop_index('idx_replies_account_id', table_name='replies')
    op.drop_index('idx_replies_lead_id', table_name='replies')
    op.drop_table('replies')
    
    op.drop_index('idx_lead_ai_data_quality', table_name='lead_ai_data')
    op.drop_index('idx_lead_ai_data_lead_id', table_name='lead_ai_data')
    op.drop_table('lead_ai_data')
    
    op.drop_index('idx_leads_author_id', table_name='leads')
    op.drop_index('idx_leads_created_at', table_name='leads')
    op.drop_index('idx_leads_status', table_name='leads')
    op.drop_index('idx_leads_chat_message', table_name='leads')
    op.drop_table('leads')
    
    op.drop_index('idx_chats_priority', table_name='chats')
    op.drop_index('idx_chats_tg_chat_id', table_name='chats')
    op.drop_index('idx_chats_enabled', table_name='chats')
    op.drop_table('chats')
    
    op.drop_index('idx_accounts_tg_user_id', table_name='accounts')
    op.drop_index('idx_accounts_enabled', table_name='accounts')
    op.drop_table('accounts')

