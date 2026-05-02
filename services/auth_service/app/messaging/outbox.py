"""
Функции записи событий в outbox-таблицу Auth Service.

Все функции принимают активную AsyncSession и добавляют EventOutbox-запись
в неё через session.add(). Commit делает вызывающий код в той же транзакции
с бизнес-операцией — это и обеспечивает транзакционную гарантию outbox-паттерна.

НЕЛЬЗЯ:
    - вызывать session.commit() внутри этих функций
    - открывать собственную сессию

МОЖНО:
    - использовать в любом месте, где есть активная сессия
    - вызывать несколько record_* в рамках одной транзакции
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_outbox import EventOutbox
from app.models.user import User
from app.messaging.schemas import (
    UserCreatedPayload,
    UserUpdatedPayload,
    UserDeactivatedPayload,
    RoleChangedPayload,
)


async def record_user_created(session: AsyncSession, user: User, role_name: str) -> None:
    """
    Записать событие 'user.created' в outbox.
    
    Args:
        session: активная AsyncSession (с открытой транзакцией)
        user: только что созданный User (должен иметь id, поэтому вызывать
              после flush() или после того, как ORM получил id от БД)
        role_name: имя роли (передаём явно, чтобы не делать lazy-load
                   user.role внутри outbox-логики)
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = UserCreatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        role_id=user.role_id,
        role_name=role_name,
        studio_id=user.studio_id,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="user",
        aggregate_id=str(user.id),
        event_type="user.created",
        routing_key="user.created",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)


async def record_user_updated(session: AsyncSession, user: User, role_name: str) -> None:
    """
    Записать событие 'user.updated' в outbox.
    
    Передаём ПОЛНЫЙ снимок состояния пользователя, а не diff. Consumer
    просто перезаписывает локальную копию, опираясь на occurred_at
    для отбрасывания out-of-order устаревших апдейтов.
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = UserUpdatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        role_id=user.role_id,
        role_name=role_name,
        studio_id=user.studio_id,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="user",
        aggregate_id=str(user.id),
        event_type="user.updated",
        routing_key="user.updated",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)


async def record_user_deactivated(
    session: AsyncSession,
    user_id: int,
    reason: str | None = None,
) -> None:
    """
    Записать событие 'user.deactivated' в outbox.
    
    Args:
        session: активная AsyncSession
        user_id: ID деактивируемого пользователя
        reason: опциональная причина деактивации ('locked', 'admin_action', etc.)
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = UserDeactivatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        user_id=user_id,
        reason=reason,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="user",
        aggregate_id=str(user_id),
        event_type="user.deactivated",
        routing_key="user.deactivated",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)


async def record_role_changed(
    session: AsyncSession,
    user_id: int,
    old_role_id: int,
    old_role_name: str,
    new_role_id: int,
    new_role_name: str,
    changed_by_user_id: int | None = None,
) -> None:
    """
    Записать событие 'role.changed' в outbox.
    
    Args:
        session: активная AsyncSession
        user_id: ID пользователя, у которого меняется роль
        old_role_id, old_role_name: старая роль для аудита
        new_role_id, new_role_name: новая роль
        changed_by_user_id: кто инициировал смену (None для системных операций)
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = RoleChangedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        user_id=user_id,
        old_role_id=old_role_id,
        old_role_name=old_role_name,
        new_role_id=new_role_id,
        new_role_name=new_role_name,
        changed_by_user_id=changed_by_user_id,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="user",
        aggregate_id=str(user_id),
        event_type="role.changed",
        routing_key="role.changed",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)


__all__ = [
    "record_user_created",
    "record_user_updated",
    "record_user_deactivated",
    "record_role_changed",
]