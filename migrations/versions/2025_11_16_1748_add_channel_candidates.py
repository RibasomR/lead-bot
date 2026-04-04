"""Add channel_candidates table for channel discovery

Revision ID: 2025_11_16_1748
Revises: 2024_11_15_0002
Create Date: 2025-11-16 17:48:00.000000

## Таблица для хранения кандидатов каналов найденных через автопоиск
Используется для фазы 7 - автопоиск и рекомендации каналов
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2025_11_16_1748'
down_revision: Union[str, None] = '2024_11_15_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ## Создание таблицы channel_candidates
    op.create_table(
        'channel_candidates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tg_chat_id', sa.BigInteger(), nullable=True, comment='Telegram Chat ID (если известен)'),
        sa.Column('username', sa.String(length=100), nullable=True, comment='Username канала (@channel)'),
        sa.Column('title', sa.String(length=255), nullable=False, comment='Название канала'),
        sa.Column('description', sa.Text(), nullable=True, comment='Описание канала'),
        sa.Column('invite_link', sa.String(length=500), nullable=True, comment='Ссылка-приглашение'),
        sa.Column('members_count', sa.Integer(), nullable=True, comment='Количество подписчиков'),
        sa.Column('recent_posts', sa.Text(), nullable=True, comment='JSON с последними N постами'),
        sa.Column('search_query', sa.String(length=200), nullable=True, comment='Поисковый запрос, по которому найден'),
        sa.Column('source', sa.String(length=50), nullable=False, comment='Источник данных (telegram/tgstat)'),
        sa.Column('ai_score', sa.Float(), nullable=True, comment='AI оценка релевантности (0-10)'),
        sa.Column('ai_comment', sa.Text(), nullable=True, comment='Комментарий AI'),
        sa.Column('ai_order_type', sa.String(length=100), nullable=True, comment='Тип заказов (фриланс/вакансии/стажировки)'),
        sa.Column('is_added_to_monitoring', sa.Boolean(), nullable=False, server_default='false', comment='Добавлен ли в мониторинг'),
        sa.Column('is_rejected', sa.Boolean(), nullable=False, server_default='false', comment='Отклонён оператором'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint('ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 10)', name='check_ai_score'),
        sa.CheckConstraint("source IN ('telegram', 'tgstat')", name='check_source'),
        sa.PrimaryKeyConstraint('id')
    )
    
    ## Индексы для оптимизации запросов
    op.create_index('idx_channel_candidates_username', 'channel_candidates', ['username'])
    op.create_index('idx_channel_candidates_tg_chat_id', 'channel_candidates', ['tg_chat_id'])
    op.create_index('idx_channel_candidates_ai_score', 'channel_candidates', ['ai_score'])
    op.create_index('idx_channel_candidates_added', 'channel_candidates', ['is_added_to_monitoring'])
    op.create_index('idx_channel_candidates_source_created', 'channel_candidates', ['source', 'created_at'])
    
    ## Композитный индекс для поиска непросмотренных кандидатов с высоким скором
    op.create_index(
        'idx_channel_candidates_review',
        'channel_candidates',
        ['is_added_to_monitoring', 'is_rejected', 'ai_score'],
        postgresql_where=sa.text('is_added_to_monitoring = false AND is_rejected = false')
    )


def downgrade() -> None:
    ## Удаление индексов
    op.drop_index('idx_channel_candidates_review', table_name='channel_candidates')
    op.drop_index('idx_channel_candidates_source_created', table_name='channel_candidates')
    op.drop_index('idx_channel_candidates_added', table_name='channel_candidates')
    op.drop_index('idx_channel_candidates_ai_score', table_name='channel_candidates')
    op.drop_index('idx_channel_candidates_tg_chat_id', table_name='channel_candidates')
    op.drop_index('idx_channel_candidates_username', table_name='channel_candidates')
    
    ## Удаление таблицы
    op.drop_table('channel_candidates')

