"""
Обработчики событий из exchange 'auth_events' (Auth Service).

Каждый handler:
    1. Проверяет идемпотентность через таблицу processed_events.
       Если event_id уже обработан - пропускает.
    2. Применяет изменение к users_cache (upsert).
    3. Записывает event_id в processed_events.
    4. Всё в одной транзакции - либо всё, либо ничего.

Out-of-order защита:
    Если приходит более старое событие (occurred_at < users_cache.updated_at) -
    игнорируем его, чтобы не откатить более свежие данные.
    Этот сценарий редкий, но возможен при ретраях publisher'а.

Soft-delete для деактивации:
    user.deactivated НЕ удаляет запись из users_cache - просто ставит is_active=false.
    Запись остаётся, потому что lesson.teacher_id и lesson.student_ids ссылаются
    на эти id, и удаление сломает целостность исторических данных.
"""

import logging
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AsyncSessionLocal
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
    # ISO 8601 строка от publisher'а
    return datetime.fromisoformat(raw)


async def _get_existing_user(session: AsyncSession, user_id: int) -> UserCache | None:
    """Получить текущую запись из users_cache."""
    result = await session.execute(
        select(UserCache).where(UserCache.id == user_id)
    )
    return result.scalar_one_or_none()


async def handle_user_created(event: Dict[str, Any]) -> None:
    """
    Обработать событие 'user.created'.
    
    Создаёт новую запись в users_cache. Если запись уже существует
    (например, бутстрап-скрипт уже её создал) - upsert обновляет данные.
    """
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    
    async with AsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            # Upsert: при коллизии по PK - обновляем поля.
            # Это даёт идемпотентность даже если processed_events почему-то не сработал.
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
                # Не перезаписываем более свежее состояние более старым событием
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
            # PK-конфликт в processed_events = событие пришло параллельно дважды.
            # Это нормально для at-least-once, просто пропускаем.
            await session.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)


async def handle_user_updated(event: Dict[str, Any]) -> None:
    """
    Обработать событие 'user.updated'.
    
    Полный snapshot пользователя в payload - просто перезаписываем поля.
    Если событие старее текущей записи (out-of-order) - игнорируем.
    """
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]
    
    async with AsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_user(session, user_id)
            
            if existing is None:
                # user.updated пришло до user.created - возможно, потерялось created
                # или порядок нарушен. Создаём запись на лету (upsert), это безопасно.
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
    """
    Обработать событие 'user.deactivated'.
    
    Soft-delete: проставляем is_active=false. Запись остаётся в кеше для целостности
    исторических связей (lessons ссылаются на teacher_id/student_ids).
    """
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]
    
    async with AsyncSessionLocal() as session:
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
    """
    Обработать событие 'role.changed'.
    
    Обновляет role_id и role_name. Аудит-поля (old_role_*) логируем,
    но в users_cache не храним - это задача audit log в Auth Service.
    """
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]
    
    async with AsyncSessionLocal() as session:
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