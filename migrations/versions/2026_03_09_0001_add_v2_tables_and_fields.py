"""v2: Добавить таблицы freelancer_profile, search_queries, search_global_results + новые поля в leads и lead_ai_data

Revision ID: 2026_03_09_0001
Revises: 2025_11_16_1748
Create Date: 2026-03-09 00:00:00.000000

## Фаза 1 рефакторинга v1 → v2
- FreelancerProfile (singleton): профиль для генерации автоответов
- SearchQuery: поисковые фразы для search_global
- SearchGlobalResult: дедупликация результатов глобального поиска
- leads.source, leads.draft_reply
- lead_ai_data: is_order, relevance_score, estimated_budget, tags, classifier_model, generated_reply
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2026_03_09_0001'
down_revision: Union[str, None] = '2025_11_16_1748'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ## Таблица freelancer_profile
    op.create_table(
        'freelancer_profile',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stack', sa.Text(), nullable=True, comment='Стек технологий'),
        sa.Column('specialization', sa.Text(), nullable=True, comment='Специализация'),
        sa.Column('preferences', sa.Text(), nullable=True, comment='Предпочтения'),
        sa.Column('min_budget', sa.Integer(), nullable=True, comment='Минимальный бюджет (руб)'),
        sa.Column('about', sa.Text(), nullable=True, comment='О себе'),
        sa.Column('portfolio_url', sa.String(500), nullable=True, comment='Ссылка на портфолио'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    ## Таблица search_queries
    op.create_table(
        'search_queries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('query_text', sa.String(200), nullable=False, unique=True, comment='Текст поискового запроса'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true'), comment='Активен ли'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True, comment='Последнее использование'),
        sa.Column('results_count', sa.Integer(), nullable=False, server_default=sa.text('0'), comment='Количество результатов'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_search_queries_enabled', 'search_queries', ['enabled'])

    ## Таблица search_global_results
    op.create_table(
        'search_global_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('query_id', sa.Integer(), sa.ForeignKey('search_queries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chat_tg_id', sa.BigInteger(), nullable=False, comment='Telegram Chat ID'),
        sa.Column('message_id', sa.Integer(), nullable=False, comment='ID сообщения'),
        sa.Column('message_text', sa.Text(), nullable=True, comment='Текст сообщения'),
        sa.Column('author_id', sa.BigInteger(), nullable=True, comment='ID автора'),
        sa.Column('found_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('is_processed', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='Обработано ли'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sgr_chat_message', 'search_global_results', ['chat_tg_id', 'message_id'], unique=True)
    op.create_index('idx_sgr_query_id', 'search_global_results', ['query_id'])
    op.create_index('idx_sgr_is_processed', 'search_global_results', ['is_processed'])

    ## Новые поля в leads
    op.add_column('leads', sa.Column('source', sa.String(20), nullable=False, server_default='monitor', comment='Источник: monitor | search_global'))
    op.add_column('leads', sa.Column('draft_reply', sa.Text(), nullable=True, comment='Черновик автоответа'))
    op.create_check_constraint('check_lead_source', 'leads', "source IN ('monitor', 'search_global')")
    op.create_index('idx_leads_source', 'leads', ['source'])

    ## Новые поля в lead_ai_data
    op.add_column('lead_ai_data', sa.Column('is_order', sa.Boolean(), nullable=True, comment='Это заказ?'))
    op.add_column('lead_ai_data', sa.Column('relevance_score', sa.Float(), nullable=True, comment='Релевантность (1-10)'))
    op.add_column('lead_ai_data', sa.Column('estimated_budget', sa.Text(), nullable=True, comment='Оценка бюджета'))
    op.add_column('lead_ai_data', sa.Column('tags', sa.Text(), nullable=True, comment='JSON массив тегов'))
    op.add_column('lead_ai_data', sa.Column('classifier_model', sa.String(100), nullable=True, comment='Модель классификатора'))
    op.add_column('lead_ai_data', sa.Column('generated_reply', sa.Text(), nullable=True, comment='Сгенерированный черновик'))
    op.create_check_constraint('check_relevance_score', 'lead_ai_data', 'relevance_score IS NULL OR (relevance_score >= 1 AND relevance_score <= 10)')
    op.create_index('idx_lead_ai_data_relevance', 'lead_ai_data', ['relevance_score'])


def downgrade() -> None:
    ## Откат lead_ai_data
    op.drop_index('idx_lead_ai_data_relevance', table_name='lead_ai_data')
    op.drop_constraint('check_relevance_score', 'lead_ai_data', type_='check')
    op.drop_column('lead_ai_data', 'generated_reply')
    op.drop_column('lead_ai_data', 'classifier_model')
    op.drop_column('lead_ai_data', 'tags')
    op.drop_column('lead_ai_data', 'estimated_budget')
    op.drop_column('lead_ai_data', 'relevance_score')
    op.drop_column('lead_ai_data', 'is_order')

    ## Откат leads
    op.drop_index('idx_leads_source', table_name='leads')
    op.drop_constraint('check_lead_source', 'leads', type_='check')
    op.drop_column('leads', 'draft_reply')
    op.drop_column('leads', 'source')

    ## Удаление таблиц
    op.drop_table('search_global_results')
    op.drop_table('search_queries')
    op.drop_table('freelancer_profile')
