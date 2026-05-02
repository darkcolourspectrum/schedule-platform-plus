"""
Обработчики событий из exchange 'auth_events' (Auth Service).

Каждый handler:
    1. Проверяет идемпотентность через таблицу processed_events.
    2. Применяет изменение к users_cache (upsert).
    3. Записывает event_id в processed_events.
    4. Всё в одной транзакции - либо всё, либо ничего.

Out-of-order защита: если приходит более старое событие
(occurred_at < users_cache.updated_at), оно игнорируется.

Soft-delete для деактивации: user.deactivated НЕ удаляет запись.
"""

import logging
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal
from app.models.user_cache import UserCache
from app.models.processed_event import ProcessedEvent

logger = logging.getLogger(__name__)


async def _is_already_processed(session: AsyncSession, event_id: UUID) -> bool:
    """Проверить, обрабатывалось ли уже событие с таким event_id."""
    result = await session.execute(
        select(ProcessedEvent.event_id).where(ProcessedEvent.event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_processed(
    session: AsyncSession,
    event_id: UUID,
    event_type: str,
) -> None:
    """Записать event_id в processed_events. Не коммитит."""
    session.add(ProcessedEvent(event_id=event_id, event_type=event_type))


def _parse_occurred_at(event: Dict[str, Any]) -> datetime:
    """Извлечь и распарсить occurred_at из payload события."""
    raw = event["occurred_at"]
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(raw)


async def _get_existing_user(session: AsyncSession, user_id: int) -> UserCache | None:
    """Получить текущую запись из users_cache."""
    result = await session.execute(
        select(UserCache).where(UserCache.id == user_id)
    )
    return result.scalar_one_or_none()


async def handle_user_created(event: Dict[str, Any]) -> None:
    """Обработать событие 'user.created'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    
    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            stmt = pg_insert(UserCache).values(
                id=event["user_id"],
                email=event["email"],
                first_name=event["first_name"],
                last_name=event["last_name"],
                phone=event.get("phone"),
                role_id=event["role_id"],
                role_name=event["role_name"],
                studio_id=event.get("studio_id"),
                is_active=event["is_active"],
                is_verified=event["is_verified"],
                updated_at=occurred_at,
                synced_at=datetime.utcnow(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "email": stmt.excluded.email,
                    "first_name": stmt.excluded.first_name,
                    "last_name": stmt.excluded.last_name,
                    "phone": stmt.excluded.phone,
                    "role_id": stmt.excluded.role_id,
                    "role_name": stmt.excluded.role_name,
                    "studio_id": stmt.excluded.studio_id,
                    "is_active": stmt.excluded.is_active,
                    "is_verified": stmt.excluded.is_verified,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=UserCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)
            
            await _mark_processed(session, event_id, "user.created")
            await session.commit()
            
            logger.info(
                "user.created applied: user_id=%s event_id=%s",
                event["user_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)


async def handle_user_updated(event: Dict[str, Any]) -> None:
    """Обработать событие 'user.updated'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]
    
    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_user(session, user_id)
            
            if existing is None:
                logger.warning(
                    "user.updated for unknown user_id=%s, creating new cache entry",
                    user_id,
                )
                stmt = pg_insert(UserCache).values(
                    id=user_id,
                    email=event["email"],
                    first_name=event["first_name"],
                    last_name=event["last_name"],
                    phone=event.get("phone"),
                    role_id=event["role_id"],
                    role_name=event["role_name"],
                    studio_id=event.get("studio_id"),
                    is_active=event["is_active"],
                    is_verified=event["is_verified"],
                    updated_at=occurred_at,
                    synced_at=datetime.utcnow(),
                ).on_conflict_do_nothing(index_elements=["id"])
                await session.execute(stmt)
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order user.updated: user_id=%s "
                    "existing.updated_at=%s occurred_at=%s",
                    user_id, existing.updated_at, occurred_at,
                )
            else:
                existing.email = event["email"]
                existing.first_name = event["first_name"]
                existing.last_name = event["last_name"]
                existing.phone = event.get("phone")
                existing.role_id = event["role_id"]
                existing.role_name = event["role_name"]
                existing.studio_id = event.get("studio_id")
                existing.is_active = event["is_active"]
                existing.is_verified = event["is_verified"]
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "user.updated")
            await session.commit()
            
            logger.info(
                "user.updated applied: user_id=%s event_id=%s",
                user_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)


async def handle_user_deactivated(event: Dict[str, Any]) -> None:
    """Обработать событие 'user.deactivated' (soft-delete: is_active=false)."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]
    
    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_user(session, user_id)
            
            if existing is None:
                logger.warning(
                    "user.deactivated for unknown user_id=%s, ignoring",
                    user_id,
                )
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order user.deactivated: user_id=%s",
                    user_id,
                )
            else:
                existing.is_active = False
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "user.deactivated")
            await session.commit()
            
            logger.info(
                "user.deactivated applied: user_id=%s reason=%s event_id=%s",
                user_id, event.get("reason"), event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)


async def handle_role_changed(event: Dict[str, Any]) -> None:
    """Обработать событие 'role.changed'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]
    
    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_user(session, user_id)
            
            if existing is None:
                logger.warning(
                    "role.changed for unknown user_id=%s, ignoring",
                    user_id,
                )
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order role.changed: user_id=%s",
                    user_id,
                )
            else:
                existing.role_id = event["new_role_id"]
                existing.role_name = event["new_role_name"]
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "role.changed")
            await session.commit()
            
            logger.info(
                "role.changed applied: user_id=%s %s -> %s event_id=%s",
                user_id, event.get("old_role_name"), event.get("new_role_name"),
                event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)