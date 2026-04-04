"""
## CRUD операции для всех таблиц
Базовые операции создания, чтения, обновления и удаления данных.
"""

from typing import Optional, List, Sequence
from datetime import datetime, timedelta

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.database.models import (
    Account, Chat, Lead, LeadAIData, Reply, ChannelCandidate,
    FreelancerProfile, SearchQuery, SearchGlobalResult,
    LeadStatus, CommunicationStyle, ChatType, ChannelSource
)


# ==================== ACCOUNTS ====================

async def create_account(
    session: AsyncSession,
    label: str,
    tg_user_id: int,
    phone: Optional[str] = None,
    username: Optional[str] = None,
    style_default: str = CommunicationStyle.FRIENDLY.value,
    enabled: bool = True
) -> Account:
    """Создать новый аккаунт"""
    account = Account(
        label=label,
        tg_user_id=tg_user_id,
        phone=phone,
        username=username,
        style_default=style_default,
        enabled=enabled
    )
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


async def get_account_by_id(session: AsyncSession, account_id: int) -> Optional[Account]:
    """Получить аккаунт по ID"""
    result = await session.execute(select(Account).where(Account.id == account_id))
    return result.scalar_one_or_none()


async def get_account_by_label(session: AsyncSession, label: str) -> Optional[Account]:
    """Получить аккаунт по label"""
    result = await session.execute(select(Account).where(Account.label == label))
    return result.scalar_one_or_none()


async def get_account_by_tg_id(session: AsyncSession, tg_user_id: int) -> Optional[Account]:
    """Получить аккаунт по Telegram User ID"""
    result = await session.execute(select(Account).where(Account.tg_user_id == tg_user_id))
    return result.scalar_one_or_none()


async def get_all_accounts(session: AsyncSession, enabled_only: bool = False) -> Sequence[Account]:
    """Получить все аккаунты"""
    query = select(Account)
    if enabled_only:
        query = query.where(Account.enabled == True)
    query = query.order_by(Account.id)
    result = await session.execute(query)
    return result.scalars().all()


async def update_account_status(session: AsyncSession, account_id: int, enabled: bool) -> bool:
    """Обновить статус аккаунта"""
    result = await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(enabled=enabled, updated_at=datetime.utcnow())
    )
    await session.flush()
    return result.rowcount > 0


async def update_account_tg_data(
    session: AsyncSession,
    account_id: int,
    tg_user_id: Optional[int] = None,
    username: Optional[str] = None
) -> bool:
    """Обновить Telegram данные аккаунта (ID и username)"""
    values = {"updated_at": datetime.utcnow()}
    if tg_user_id is not None:
        values["tg_user_id"] = tg_user_id
    if username is not None:
        values["username"] = username
    
    result = await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(**values)
    )
    await session.flush()
    return result.rowcount > 0


async def delete_account(session: AsyncSession, account_id: int) -> bool:
    """Удалить аккаунт"""
    result = await session.execute(delete(Account).where(Account.id == account_id))
    await session.flush()
    return result.rowcount > 0


# ==================== CHATS ====================

async def create_chat(
    session: AsyncSession,
    tg_chat_id: int,
    title: str,
    chat_type: str,
    username: Optional[str] = None,
    priority: int = 1,
    is_whitelisted: bool = True,  ## По умолчанию все добавленные чаты одобрены
    is_blacklisted: bool = False,
    enabled: bool = True
) -> Chat:
    """
    ## Создать новый чат
    
    По умолчанию is_whitelisted=True, т.к. если чат добавляется вручную,
    значит он нужен для мониторинга.
    """
    chat = Chat(
        tg_chat_id=tg_chat_id,
        title=title,
        username=username,
        type=chat_type,
        priority=priority,
        is_whitelisted=is_whitelisted,
        is_blacklisted=is_blacklisted,
        enabled=enabled
    )
    session.add(chat)
    await session.flush()
    await session.refresh(chat)
    return chat


async def get_chat_by_id(session: AsyncSession, chat_id: int) -> Optional[Chat]:
    """Получить чат по ID"""
    result = await session.execute(select(Chat).where(Chat.id == chat_id))
    return result.scalar_one_or_none()


async def get_chat_by_tg_id(session: AsyncSession, tg_chat_id: int) -> Optional[Chat]:
    """Получить чат по Telegram Chat ID"""
    result = await session.execute(select(Chat).where(Chat.tg_chat_id == tg_chat_id))
    return result.scalar_one_or_none()


async def get_all_chats(
    session: AsyncSession, 
    enabled_only: bool = False,
    exclude_blacklisted: bool = True
) -> Sequence[Chat]:
    """Получить все чаты"""
    query = select(Chat)
    
    if enabled_only:
        query = query.where(Chat.enabled == True)
    if exclude_blacklisted:
        query = query.where(Chat.is_blacklisted == False)
    
    query = query.order_by(Chat.priority.desc(), Chat.id)
    result = await session.execute(query)
    return result.scalars().all()


async def update_chat_status(session: AsyncSession, chat_id: int, enabled: bool) -> bool:
    """Обновить статус мониторинга чата"""
    result = await session.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(enabled=enabled, updated_at=datetime.utcnow())
    )
    await session.flush()
    return result.rowcount > 0


async def update_chat_whitelist(session: AsyncSession, chat_id: int, is_whitelisted: bool) -> bool:
    """Добавить/убрать чат из белого списка"""
    result = await session.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(is_whitelisted=is_whitelisted, updated_at=datetime.utcnow())
    )
    await session.flush()
    return result.rowcount > 0


async def update_chat_blacklist(session: AsyncSession, chat_id: int, is_blacklisted: bool) -> bool:
    """Добавить/убрать чат из чёрного списка"""
    result = await session.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(is_blacklisted=is_blacklisted, updated_at=datetime.utcnow())
    )
    await session.flush()
    return result.rowcount > 0


async def delete_chat(session: AsyncSession, chat_id: int) -> bool:
    """Удалить чат"""
    result = await session.execute(delete(Chat).where(Chat.id == chat_id))
    await session.flush()
    return result.rowcount > 0


# ==================== LEADS ====================

async def create_lead(
    session: AsyncSession,
    chat_id: int,
    message_id: int,
    message_text: str,
    author_id: Optional[int] = None,
    author_username: Optional[str] = None,
    author_name: Optional[str] = None,
    message_url: Optional[str] = None,
    language: str = "ru",
    stack_tags: Optional[str] = None,
    status: str = LeadStatus.NEW.value,
    source: str = "monitor",
    draft_reply: Optional[str] = None
) -> Lead:
    """Создать новый лид"""
    lead = Lead(
        chat_id=chat_id,
        message_id=message_id,
        message_text=message_text,
        author_id=author_id,
        author_username=author_username,
        author_name=author_name,
        message_url=message_url,
        language=language,
        stack_tags=stack_tags,
        status=status,
        source=source,
        draft_reply=draft_reply
    )
    session.add(lead)
    await session.flush()
    await session.refresh(lead)
    return lead


async def get_lead_by_id(
    session: AsyncSession, 
    lead_id: int,
    load_relations: bool = False
) -> Optional[Lead]:
    """Получить лид по ID"""
    query = select(Lead).where(Lead.id == lead_id)
    
    if load_relations:
        query = query.options(
            selectinload(Lead.chat),
            selectinload(Lead.ai_data),
            selectinload(Lead.replies)
        )
    
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_lead_by_chat_message(
    session: AsyncSession,
    chat_id: int,
    message_id: int
) -> Optional[Lead]:
    """Получить лид по chat_id и message_id (проверка дубликатов)"""
    result = await session.execute(
        select(Lead).where(
            and_(Lead.chat_id == chat_id, Lead.message_id == message_id)
        )
    )
    return result.scalar_one_or_none()


async def get_all_leads(
    session: AsyncSession,
    limit: int = 1000,
    offset: int = 0,
    exclude_ignored: bool = True
) -> Sequence[Lead]:
    """
    ## Получить все лиды (упорядоченные по дате создания, новые первыми)

    Args:
        session: Сессия БД
        limit: Максимальное количество лидов
        offset: Смещение
        exclude_ignored: Исключить игнорированные лиды (по умолчанию True)

    Returns:
        Список лидов
    """
    query = select(Lead)
    if exclude_ignored:
        query = query.where(Lead.status != "ignored")
    query = query.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return result.scalars().all()


async def get_leads_by_status(
    session: AsyncSession,
    status: str,
    limit: int = 100,
    offset: int = 0
) -> Sequence[Lead]:
    """Получить лиды по статусу"""
    query = (
        select(Lead)
        .where(Lead.status == status)
        .order_by(Lead.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    return result.scalars().all()


async def get_leads_by_date_range(
    session: AsyncSession,
    start_date: datetime,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    exclude_ignored: bool = True
) -> Sequence[Lead]:
    """Получить лиды за период"""
    query = select(Lead).where(Lead.created_at >= start_date)

    if end_date:
        query = query.where(Lead.created_at <= end_date)
    if status:
        query = query.where(Lead.status == status)
    if exclude_ignored and not status:
        query = query.where(Lead.status != "ignored")

    query = query.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return result.scalars().all()


async def update_lead_status(
    session: AsyncSession,
    lead_id: int,
    status: str
) -> bool:
    """Обновить статус лида"""
    result = await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(status=status, updated_at=datetime.utcnow())
    )
    await session.flush()
    return result.rowcount > 0


## Обновление произвольных полей лида
async def update_lead(
    session: AsyncSession,
    lead_id: int,
    **updates
) -> bool:
    """Обновить произвольные поля лида"""
    updates["updated_at"] = datetime.utcnow()
    result = await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(**updates)
    )
    await session.flush()
    return result.rowcount > 0


async def count_leads_by_status(session: AsyncSession, status: str) -> int:
    """Подсчитать количество лидов по статусу"""
    result = await session.execute(
        select(func.count()).select_from(Lead).where(Lead.status == status)
    )
    return result.scalar_one()


# ==================== LEAD AI DATA ====================

async def create_lead_ai_data(
    session: AsyncSession,
    lead_id: int,
    summary: Optional[str] = None,
    quality_score: Optional[float] = None,
    tone_recommendation: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    reply_variants: Optional[str] = None,
    raw_response: Optional[str] = None,
    ai_model_used: Optional[str] = None
) -> LeadAIData:
    """Создать AI данные для лида"""
    ai_data = LeadAIData(
        lead_id=lead_id,
        summary=summary,
        quality_score=quality_score,
        tone_recommendation=tone_recommendation,
        price_min=price_min,
        price_max=price_max,
        reply_variants=reply_variants,
        raw_response=raw_response,
        ai_model_used=ai_model_used
    )
    session.add(ai_data)
    await session.flush()
    await session.refresh(ai_data)
    return ai_data


async def get_lead_ai_data(session: AsyncSession, lead_id: int) -> Optional[LeadAIData]:
    """Получить AI данные по lead_id"""
    result = await session.execute(
        select(LeadAIData).where(LeadAIData.lead_id == lead_id)
    )
    return result.scalar_one_or_none()


async def update_lead_ai_data(
    session: AsyncSession,
    lead_id: int,
    **updates
) -> bool:
    """Обновить AI данные лида"""
    updates["updated_at"] = datetime.utcnow()
    result = await session.execute(
        update(LeadAIData)
        .where(LeadAIData.lead_id == lead_id)
        .values(**updates)
    )
    await session.flush()
    return result.rowcount > 0


async def delete_lead_ai_data(session: AsyncSession, lead_id: int) -> bool:
    """Удалить AI данные"""
    result = await session.execute(
        delete(LeadAIData).where(LeadAIData.lead_id == lead_id)
    )
    await session.flush()
    return result.rowcount > 0


# ==================== REPLIES ====================

async def create_reply(
    session: AsyncSession,
    lead_id: int,
    account_id: int,
    style_used: str,
    reply_text: str,
    fast_mode_used: bool = False,
    was_successful: bool = True,
    error_message: Optional[str] = None
) -> Reply:
    """Создать запись об отправленном ответе"""
    reply = Reply(
        lead_id=lead_id,
        account_id=account_id,
        style_used=style_used,
        reply_text=reply_text,
        fast_mode_used=fast_mode_used,
        was_successful=was_successful,
        error_message=error_message
    )
    session.add(reply)
    await session.flush()
    await session.refresh(reply)
    return reply


async def get_reply_by_id(session: AsyncSession, reply_id: int) -> Optional[Reply]:
    """Получить ответ по ID"""
    result = await session.execute(select(Reply).where(Reply.id == reply_id))
    return result.scalar_one_or_none()


async def get_replies_by_lead(session: AsyncSession, lead_id: int) -> Sequence[Reply]:
    """Получить все ответы на лид"""
    query = select(Reply).where(Reply.lead_id == lead_id).order_by(Reply.sent_at)
    result = await session.execute(query)
    return result.scalars().all()


async def get_replies_by_account(
    session: AsyncSession,
    account_id: int,
    limit: int = 100,
    offset: int = 0
) -> Sequence[Reply]:
    """Получить ответы конкретного аккаунта"""
    query = (
        select(Reply)
        .where(Reply.account_id == account_id)
        .order_by(Reply.sent_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    return result.scalars().all()


async def count_replies_in_timeframe(
    session: AsyncSession,
    account_id: int,
    chat_id: int,
    hours: int = 1
) -> int:
    """
    ## Оптимизированный подсчёт ответов за последние N часов
    Используется для антиспам-проверок.
    Оптимизация: JOIN вместо подзапроса для лучшей производительности.
    """
    time_threshold = datetime.utcnow() - timedelta(hours=hours)
    
    result = await session.execute(
        select(func.count())
        .select_from(Reply)
        .join(Lead, Reply.lead_id == Lead.id)
        .where(
            and_(
                Reply.account_id == account_id,
                Lead.chat_id == chat_id,
                Reply.sent_at >= time_threshold,
                Reply.was_successful == True
            )
        )
    )
    return result.scalar_one()


async def get_recent_replies(
    session: AsyncSession,
    hours: int = 24,
    limit: int = 100
) -> Sequence[Reply]:
    """Получить недавние ответы"""
    time_threshold = datetime.utcnow() - timedelta(hours=hours)
    query = (
        select(Reply)
        .where(Reply.sent_at >= time_threshold)
        .order_by(Reply.sent_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return result.scalars().all()


# ==================== СТАТИСТИКА ====================

async def get_leads_statistics(session: AsyncSession) -> dict:
    """Получить общую статистику по лидам"""
    total = await session.execute(select(func.count()).select_from(Lead))
    new = await session.execute(
        select(func.count()).select_from(Lead).where(Lead.status == LeadStatus.NEW.value)
    )
    viewed = await session.execute(
        select(func.count()).select_from(Lead).where(Lead.status == LeadStatus.VIEWED.value)
    )
    replied = await session.execute(
        select(func.count()).select_from(Lead).where(Lead.status == LeadStatus.REPLIED.value)
    )
    ignored = await session.execute(
        select(func.count()).select_from(Lead).where(Lead.status == LeadStatus.IGNORED.value)
    )
    
    return {
        "total": total.scalar_one(),
        "new": new.scalar_one(),
        "viewed": viewed.scalar_one(),
        "replied": replied.scalar_one(),
        "ignored": ignored.scalar_one()
    }


async def get_account_statistics(session: AsyncSession, account_id: int) -> dict:
    """Получить статистику по аккаунту"""
    total_replies = await session.execute(
        select(func.count()).select_from(Reply).where(Reply.account_id == account_id)
    )
    successful_replies = await session.execute(
        select(func.count())
        .select_from(Reply)
        .where(and_(Reply.account_id == account_id, Reply.was_successful == True))
    )
    
    return {
        "total_replies": total_replies.scalar_one(),
        "successful_replies": successful_replies.scalar_one()
    }


# ==================== CHANNEL CANDIDATES (автопоиск каналов) ====================

async def create_channel_candidate(
    session: AsyncSession,
    title: str,
    source: str,
    tg_chat_id: Optional[int] = None,
    username: Optional[str] = None,
    description: Optional[str] = None,
    invite_link: Optional[str] = None,
    members_count: Optional[int] = None,
    recent_posts: Optional[str] = None,
    search_query: Optional[str] = None
) -> ChannelCandidate:
    """Создать нового кандидата канала"""
    candidate = ChannelCandidate(
        tg_chat_id=tg_chat_id,
        username=username,
        title=title,
        description=description,
        invite_link=invite_link,
        members_count=members_count,
        recent_posts=recent_posts,
        search_query=search_query,
        source=source
    )
    session.add(candidate)
    await session.flush()
    await session.refresh(candidate)
    return candidate


async def get_channel_candidate_by_id(
    session: AsyncSession, 
    candidate_id: int
) -> Optional[ChannelCandidate]:
    """Получить кандидата по ID"""
    result = await session.execute(
        select(ChannelCandidate).where(ChannelCandidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


async def get_channel_candidate_by_username(
    session: AsyncSession, 
    username: str
) -> Optional[ChannelCandidate]:
    """Получить кандидата по username"""
    result = await session.execute(
        select(ChannelCandidate).where(ChannelCandidate.username == username)
    )
    return result.scalar_one_or_none()


async def get_channel_candidate_by_tg_id(
    session: AsyncSession, 
    tg_chat_id: int
) -> Optional[ChannelCandidate]:
    """Получить кандидата по Telegram Chat ID"""
    result = await session.execute(
        select(ChannelCandidate).where(ChannelCandidate.tg_chat_id == tg_chat_id)
    )
    return result.scalar_one_or_none()


async def get_pending_candidates(
    session: AsyncSession,
    min_score: Optional[float] = None,
    limit: int = 50
) -> Sequence[ChannelCandidate]:
    """
    ## Получить непросмотренных кандидатов (не добавленных и не отклонённых)
    Опционально фильтровать по минимальному AI score
    """
    query = select(ChannelCandidate).where(
        and_(
            ChannelCandidate.is_added_to_monitoring == False,
            ChannelCandidate.is_rejected == False
        )
    )
    
    if min_score is not None:
        query = query.where(ChannelCandidate.ai_score >= min_score)
    
    query = query.order_by(ChannelCandidate.ai_score.desc()).limit(limit)
    
    result = await session.execute(query)
    return result.scalars().all()


async def get_all_candidates(
    session: AsyncSession,
    source: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> Sequence[ChannelCandidate]:
    """Получить всех кандидатов с опциональной фильтрацией по источнику"""
    query = select(ChannelCandidate)
    
    if source:
        query = query.where(ChannelCandidate.source == source)
    
    query = query.order_by(ChannelCandidate.created_at.desc()).limit(limit).offset(offset)
    
    result = await session.execute(query)
    return result.scalars().all()


async def update_candidate_ai_data(
    session: AsyncSession,
    candidate_id: int,
    ai_score: float,
    ai_comment: str,
    ai_order_type: Optional[str] = None
) -> bool:
    """Обновить AI-данные кандидата"""
    result = await session.execute(
        update(ChannelCandidate)
        .where(ChannelCandidate.id == candidate_id)
        .values(
            ai_score=ai_score,
            ai_comment=ai_comment,
            ai_order_type=ai_order_type,
            updated_at=datetime.utcnow()
        )
    )
    await session.flush()
    return result.rowcount > 0


async def mark_candidate_as_added(
    session: AsyncSession,
    candidate_id: int
) -> bool:
    """Пометить кандидата как добавленного в мониторинг"""
    result = await session.execute(
        update(ChannelCandidate)
        .where(ChannelCandidate.id == candidate_id)
        .values(
            is_added_to_monitoring=True,
            updated_at=datetime.utcnow()
        )
    )
    await session.flush()
    return result.rowcount > 0


async def mark_candidate_as_rejected(
    session: AsyncSession,
    candidate_id: int
) -> bool:
    """Пометить кандидата как отклонённого"""
    result = await session.execute(
        update(ChannelCandidate)
        .where(ChannelCandidate.id == candidate_id)
        .values(
            is_rejected=True,
            updated_at=datetime.utcnow()
        )
    )
    await session.flush()
    return result.rowcount > 0


async def delete_channel_candidate(
    session: AsyncSession,
    candidate_id: int
) -> bool:
    """Удалить кандидата"""
    result = await session.execute(
        delete(ChannelCandidate).where(ChannelCandidate.id == candidate_id)
    )
    await session.flush()
    return result.rowcount > 0


async def get_candidates_statistics(session: AsyncSession) -> dict:
    """Получить статистику по кандидатам каналов"""
    total = await session.execute(select(func.count()).select_from(ChannelCandidate))
    pending = await session.execute(
        select(func.count())
        .select_from(ChannelCandidate)
        .where(
            and_(
                ChannelCandidate.is_added_to_monitoring == False,
                ChannelCandidate.is_rejected == False
            )
        )
    )
    added = await session.execute(
        select(func.count())
        .select_from(ChannelCandidate)
        .where(ChannelCandidate.is_added_to_monitoring == True)
    )
    rejected = await session.execute(
        select(func.count())
        .select_from(ChannelCandidate)
        .where(ChannelCandidate.is_rejected == True)
    )

    return {
        "total": total.scalar_one(),
        "pending": pending.scalar_one(),
        "added": added.scalar_one(),
        "rejected": rejected.scalar_one()
    }


# ==================== FREELANCER PROFILE ====================

async def get_freelancer_profile(session: AsyncSession) -> Optional[FreelancerProfile]:
    """Получить профиль фрилансера (singleton)"""
    result = await session.execute(select(FreelancerProfile).limit(1))
    return result.scalar_one_or_none()


async def create_or_update_freelancer_profile(
    session: AsyncSession,
    stack: Optional[str] = None,
    specialization: Optional[str] = None,
    preferences: Optional[str] = None,
    min_budget: Optional[int] = None,
    about: Optional[str] = None,
    portfolio_url: Optional[str] = None
) -> FreelancerProfile:
    """Создать или обновить профиль фрилансера"""
    profile = await get_freelancer_profile(session)

    if profile:
        values = {"updated_at": datetime.utcnow()}
        if stack is not None:
            values["stack"] = stack
        if specialization is not None:
            values["specialization"] = specialization
        if preferences is not None:
            values["preferences"] = preferences
        if min_budget is not None:
            values["min_budget"] = min_budget
        if about is not None:
            values["about"] = about
        if portfolio_url is not None:
            values["portfolio_url"] = portfolio_url

        await session.execute(
            update(FreelancerProfile)
            .where(FreelancerProfile.id == profile.id)
            .values(**values)
        )
        await session.flush()
        await session.refresh(profile)
        return profile
    else:
        profile = FreelancerProfile(
            stack=stack,
            specialization=specialization,
            preferences=preferences,
            min_budget=min_budget,
            about=about,
            portfolio_url=portfolio_url
        )
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile


# ==================== SEARCH QUERIES ====================

async def create_search_query(
    session: AsyncSession,
    query_text: str,
    enabled: bool = True
) -> SearchQuery:
    """Создать поисковый запрос"""
    query = SearchQuery(query_text=query_text, enabled=enabled)
    session.add(query)
    await session.flush()
    await session.refresh(query)
    return query


async def get_search_query_by_id(session: AsyncSession, query_id: int) -> Optional[SearchQuery]:
    """Получить поисковый запрос по ID"""
    result = await session.execute(select(SearchQuery).where(SearchQuery.id == query_id))
    return result.scalar_one_or_none()


async def get_all_search_queries(
    session: AsyncSession,
    enabled_only: bool = False
) -> Sequence[SearchQuery]:
    """Получить все поисковые запросы"""
    stmt = select(SearchQuery)
    if enabled_only:
        stmt = stmt.where(SearchQuery.enabled == True)
    stmt = stmt.order_by(SearchQuery.id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_todays_search_queries(session: AsyncSession) -> Sequence[SearchQuery]:
    """Выбрать 10 фраз на сегодня (ротация по дням, цикл)."""
    from datetime import date

    stmt = (
        select(SearchQuery)
        .where(SearchQuery.enabled == True)
        .order_by(SearchQuery.id)
    )
    result = await session.execute(stmt)
    all_queries = list(result.scalars().all())

    if not all_queries:
        return []

    batch_size = 10
    total_batches = (len(all_queries) + batch_size - 1) // batch_size
    day_index = date.today().toordinal() % total_batches
    start = day_index * batch_size
    return all_queries[start : start + batch_size]


async def import_search_phrases(session: AsyncSession, file_path: str) -> int:
    """Импорт фраз из текстового файла (пропускает комментарии, дубликаты)."""
    from pathlib import Path

    lines = Path(file_path).read_text(encoding="utf-8").splitlines()
    imported = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        existing = await session.execute(
            select(SearchQuery).where(SearchQuery.query_text == line)
        )
        if existing.scalar_one_or_none():
            continue
        session.add(SearchQuery(query_text=line, enabled=True))
        imported += 1
    await session.flush()
    return imported


async def update_search_query_status(session: AsyncSession, query_id: int, enabled: bool) -> bool:
    """Включить/выключить поисковый запрос"""
    result = await session.execute(
        update(SearchQuery).where(SearchQuery.id == query_id).values(enabled=enabled)
    )
    await session.flush()
    return result.rowcount > 0


async def update_search_query_usage(
    session: AsyncSession,
    query_id: int,
    results_count: int
) -> bool:
    """Обновить статистику использования запроса"""
    result = await session.execute(
        update(SearchQuery)
        .where(SearchQuery.id == query_id)
        .values(last_used_at=datetime.utcnow(), results_count=results_count)
    )
    await session.flush()
    return result.rowcount > 0


async def delete_search_query(session: AsyncSession, query_id: int) -> bool:
    """Удалить поисковый запрос"""
    result = await session.execute(delete(SearchQuery).where(SearchQuery.id == query_id))
    await session.flush()
    return result.rowcount > 0


# ==================== SEARCH GLOBAL RESULTS ====================

async def create_search_global_result(
    session: AsyncSession,
    query_id: int,
    chat_tg_id: int,
    message_id: int,
    message_text: Optional[str] = None,
    author_id: Optional[int] = None
) -> Optional[SearchGlobalResult]:
    """Создать результат глобального поиска (дедупликация по chat+message)"""
    existing = await session.execute(
        select(SearchGlobalResult).where(
            and_(
                SearchGlobalResult.chat_tg_id == chat_tg_id,
                SearchGlobalResult.message_id == message_id
            )
        )
    )
    if existing.scalar_one_or_none():
        return None

    result = SearchGlobalResult(
        query_id=query_id,
        chat_tg_id=chat_tg_id,
        message_id=message_id,
        message_text=message_text,
        author_id=author_id
    )
    session.add(result)
    await session.flush()
    await session.refresh(result)
    return result


async def get_unprocessed_search_results(
    session: AsyncSession,
    limit: int = 50
) -> Sequence[SearchGlobalResult]:
    """Получить необработанные результаты поиска"""
    stmt = (
        select(SearchGlobalResult)
        .where(SearchGlobalResult.is_processed == False)
        .order_by(SearchGlobalResult.found_at)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_search_result_processed(session: AsyncSession, result_id: int) -> bool:
    """Пометить результат поиска как обработанный"""
    result = await session.execute(
        update(SearchGlobalResult)
        .where(SearchGlobalResult.id == result_id)
        .values(is_processed=True)
    )
    await session.flush()
    return result.rowcount > 0


async def count_search_queries_today(session: AsyncSession) -> int:
    """Посчитать количество поисковых запросов за сегодня (для лимита Premium)"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.count())
        .select_from(SearchQuery)
        .where(
            and_(
                SearchQuery.last_used_at is not None,
                SearchQuery.last_used_at >= today_start
            )
        )
    )
    return result.scalar_one()

