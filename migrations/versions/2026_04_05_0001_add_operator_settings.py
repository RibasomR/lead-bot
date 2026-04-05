"""Добавить таблицу operator_settings для хранения языка оператора

Revision ID: 2026_04_05_0001
Revises: 2026_03_09_0001
Create Date: 2026-04-05 00:00:00.000000

## Мультиязычность: таблица настроек оператора (язык интерфейса)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2026_04_05_0001'
down_revision: Union[str, None] = '2026_03_09_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'operator_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False, comment='Telegram User ID оператора'),
        sa.Column('language', sa.String(10), nullable=False, server_default='ru', comment='Язык интерфейса: ru / en'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id')
    )
    op.create_index('idx_operator_settings_tg_id', 'operator_settings', ['telegram_id'])


def downgrade() -> None:
    op.drop_index('idx_operator_settings_tg_id', table_name='operator_settings')
    op.drop_table('operator_settings')
