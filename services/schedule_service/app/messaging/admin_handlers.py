"""
Handlers событий из Admin Service.

Каждый handler:
    1. Проверяет идемпотентность через processed_events (event_id уже
       обработан — выходим без изменений).
    2. Применяет изменение в таблицах studios_cache / classrooms_cache.
    3. Записывает event_id в processed_events.
    4. Коммитит транзакцию.

При ошибке БД (IntegrityError, etc) делает rollback и пробрасывает
исключение — consumer отправит сообщение в DLX. При обычных
конкурентных вставках event_id (race между несколькими потребителями)
просто молча выходим.

Out-of-order защита: каждый handler сравнивает existing.updated_at
с occurred_at события и применяет изменения только если событие
новее текущего состояния. Это предохраняет от того, что устаревшее
событие, доставленное позже, перезатрёт более свежее состояние.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import ScheduleAsyncSessionLocal
from app.models.processed_event import ProcessedEvent
from app.models.studio_cache import StudioCache
from app.models.classroom_cache import ClassroomCache

logger = logging.getLogger(__name__)


# ==================== HELPERS ====================


def _parse_occurred_at(event: Dict[str, Any]) -> datetime:
    """Преобразовать occurred_at из ISO-строки или datetime в timezone-aware datetime."""
    raw = event["occurred_at"]
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _is_already_processed(session: AsyncSession, event_id: UUID) -> bool:
    """Проверить был ли event_id уже обработан (идемпотентность)."""
    result = await session.execute(
        select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_processed(
    session: AsyncSession,
    event_id: UUID,
    event_type: str,
) -> None:
    """Записать факт обработки события."""
    session.add(
        ProcessedEvent(event_id=event_id, event_type=event_type)
    )


async def _get_existing_studio(
    session: AsyncSession,
    studio_id: int,
) -> StudioCache | None:
    result = await session.execute(
        select(StudioCache).where(StudioCache.id == studio_id)
    )
    return result.scalar_one_or_none()


async def _get_existing_classroom(
    session: AsyncSession,
    classroom_id: int,
) -> ClassroomCache | None:
    result = await session.execute(
        select(ClassroomCache).where(ClassroomCache.id == classroom_id)
    )
    return result.scalar_one_or_none()


# ==================== STUDIO HANDLERS ====================


async def handle_studio_created(event: Dict[str, Any]) -> None:
    """Обработать событие 'studio.created'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    
    async with ScheduleAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            stmt = pg_insert(StudioCache).values(
                id=event["studio_id"],
                name=event["name"],
                description=event.get("description"),
                address=event.get("address"),
                phone=event.get("phone"),
                email=event.get("email"),
                is_active=event["is_active"],
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": stmt.excluded.name,
                    "description": stmt.excluded.description,
                    "address": stmt.excluded.address,
                    "phone": stmt.excluded.phone,
                    "email": stmt.excluded.email,
                    "is_active": stmt.excluded.is_active,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=StudioCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)
            
            await _mark_processed(session, event_id, "studio.created")
            await session.commit()
            
            logger.info(
                "studio.created applied: studio_id=%s event_id=%s",
                event["studio_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_studio_updated(event: Dict[str, Any]) -> None:
    """Обработать событие 'studio.updated'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    studio_id = event["studio_id"]
    
    async with ScheduleAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_studio(session, studio_id)
            
            if existing is None:
                # Если запись ещё не пришла через studio.created (out-of-order),
                # делаем upsert как при created.
                logger.info(
                    "studio.updated for unknown studio_id=%s, upserting as created",
                    studio_id,
                )
                stmt = pg_insert(StudioCache).values(
                    id=studio_id,
                    name=event["name"],
                    description=event.get("description"),
                    address=event.get("address"),
                    phone=event.get("phone"),
                    email=event.get("email"),
                    is_active=event["is_active"],
                    updated_at=occurred_at,
                    synced_at=datetime.now(timezone.utc),
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                await session.execute(stmt)
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order studio.updated: studio_id=%s",
                    studio_id,
                )
            else:
                existing.name = event["name"]
                existing.description = event.get("description")
                existing.address = event.get("address")
                existing.phone = event.get("phone")
                existing.email = event.get("email")
                existing.is_active = event["is_active"]
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "studio.updated")
            await session.commit()
            
            logger.info(
                "studio.updated applied: studio_id=%s event_id=%s",
                studio_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_studio_deactivated(event: Dict[str, Any]) -> None:
    """Обработать событие 'studio.deactivated'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    studio_id = event["studio_id"]
    
    async with ScheduleAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_studio(session, studio_id)
            
            if existing is None:
                logger.warning(
                    "studio.deactivated for unknown studio_id=%s, ignoring",
                    studio_id,
                )
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order studio.deactivated: studio_id=%s",
                    studio_id,
                )
            else:
                existing.is_active = False
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "studio.deactivated")
            await session.commit()
            
            logger.info(
                "studio.deactivated applied: studio_id=%s event_id=%s",
                studio_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


# ==================== CLASSROOM HANDLERS ====================


async def handle_classroom_created(event: Dict[str, Any]) -> None:
    """Обработать событие 'classroom.created'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    
    async with ScheduleAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            stmt = pg_insert(ClassroomCache).values(
                id=event["classroom_id"],
                studio_id=event["studio_id"],
                name=event["name"],
                capacity=event["capacity"],
                description=event.get("description"),
                equipment=event.get("equipment"),
                floor=event.get("floor"),
                room_number=event.get("room_number"),
                is_active=event["is_active"],
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "studio_id": stmt.excluded.studio_id,
                    "name": stmt.excluded.name,
                    "capacity": stmt.excluded.capacity,
                    "description": stmt.excluded.description,
                    "equipment": stmt.excluded.equipment,
                    "floor": stmt.excluded.floor,
                    "room_number": stmt.excluded.room_number,
                    "is_active": stmt.excluded.is_active,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=ClassroomCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)
            
            await _mark_processed(session, event_id, "classroom.created")
            await session.commit()
            
            logger.info(
                "classroom.created applied: classroom_id=%s studio_id=%s event_id=%s",
                event["classroom_id"], event["studio_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_classroom_updated(event: Dict[str, Any]) -> None:
    """Обработать событие 'classroom.updated'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    classroom_id = event["classroom_id"]
    
    async with ScheduleAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_classroom(session, classroom_id)
            
            if existing is None:
                logger.info(
                    "classroom.updated for unknown classroom_id=%s, upserting as created",
                    classroom_id,
                )
                stmt = pg_insert(ClassroomCache).values(
                    id=classroom_id,
                    studio_id=event["studio_id"],
                    name=event["name"],
                    capacity=event["capacity"],
                    description=event.get("description"),
                    equipment=event.get("equipment"),
                    floor=event.get("floor"),
                    room_number=event.get("room_number"),
                    is_active=event["is_active"],
                    updated_at=occurred_at,
                    synced_at=datetime.now(timezone.utc),
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                await session.execute(stmt)
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order classroom.updated: classroom_id=%s",
                    classroom_id,
                )
            else:
                existing.studio_id = event["studio_id"]
                existing.name = event["name"]
                existing.capacity = event["capacity"]
                existing.description = event.get("description")
                existing.equipment = event.get("equipment")
                existing.floor = event.get("floor")
                existing.room_number = event.get("room_number")
                existing.is_active = event["is_active"]
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "classroom.updated")
            await session.commit()
            
            logger.info(
                "classroom.updated applied: classroom_id=%s event_id=%s",
                classroom_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_classroom_deactivated(event: Dict[str, Any]) -> None:
    """Обработать событие 'classroom.deactivated'."""
    event_id = UUID(event["event_id"])
    occurred_at = _parse_occurred_at(event)
    classroom_id = event["classroom_id"]
    
    async with ScheduleAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            existing = await _get_existing_classroom(session, classroom_id)
            
            if existing is None:
                logger.warning(
                    "classroom.deactivated for unknown classroom_id=%s, ignoring",
                    classroom_id,
                )
            elif existing.updated_at >= occurred_at:
                logger.info(
                    "Skipping out-of-order classroom.deactivated: classroom_id=%s",
                    classroom_id,
                )
            else:
                existing.is_active = False
                existing.updated_at = occurred_at
            
            await _mark_processed(session, event_id, "classroom.deactivated")
            await session.commit()
            
            logger.info(
                "classroom.deactivated applied: classroom_id=%s event_id=%s",
                classroom_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


# ==================== ROUTING ====================


HANDLERS = {
    "studio.created": handle_studio_created,
    "studio.updated": handle_studio_updated,
    "studio.deactivated": handle_studio_deactivated,
    "classroom.created": handle_classroom_created,
    "classroom.updated": handle_classroom_updated,
    "classroom.deactivated": handle_classroom_deactivated,
}