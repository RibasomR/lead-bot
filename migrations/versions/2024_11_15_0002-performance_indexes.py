"""performance_indexes

Revision ID: 2024_11_15_0002
Revises: 2024_11_15_0001
Create Date: 2024-11-15 02:00:00.000000

## Добавление композитных индексов для оптимизации производительности
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2024_11_15_0002'
down_revision: Union[str, None] = '2024_11_15_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    ## Добавление композитных индексов для оптимизации запросов
    
    Оптимизации:
    1. idx_lead_ai_data_quality_created - для поиска лучших лидов по качеству и дате
    2. idx_replies_account_sent_success - для антиспам-проверок (count_replies_in_timeframe)
    """
    # Композитный индекс для LeadAIData (качество + дата создания)
    op.create_index(
        'idx_lead_ai_data_quality_created',
        'lead_ai_data',
        ['quality_score', 'created_at'],
        unique=False
    )
    
    # Композитный индекс для Replies (аккаунт + дата отправки + успешность)
    op.create_index(
        'idx_replies_account_sent_success',
        'replies',
        ['account_id', 'sent_at', 'was_successful'],
        unique=False
    )


def downgrade() -> None:
    """Откат миграции - удаление композитных индексов"""
    op.drop_index('idx_replies_account_sent_success', table_name='replies')
    op.drop_index('idx_lead_ai_data_quality_created', table_name='lead_ai_data')

