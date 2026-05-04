"""
Функции записи событий в outbox-таблицу Admin Service.

Все функции принимают активную AsyncSession и добавляют EventOutbox-запись
через session.add(). Commit делает вызывающий код в той же транзакции
с бизнес-операцией - это и обеспечивает транзакционную гарантию
outbox-паттерна.

НЕЛЬЗЯ:
    - вызывать session.commit() внутри этих функций
    - открывать собственную сессию

МОЖНО:
    - использовать в любом месте, где есть активная сессия
    - вызывать несколько record_* в рамках одной транзакции
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_outbox import EventOutbox
from app.models.studio import Studio
from app.models.classroom import Classroom
from app.messaging.schemas import (
    StudioCreatedPayload,
    StudioUpdatedPayload,
    StudioDeactivatedPayload,
    ClassroomCreatedPayload,
    ClassroomUpdatedPayload,
    ClassroomDeactivatedPayload,
)

logger = logging.getLogger(__name__)


# ==================== STUDIOS ====================


async def record_studio_created(session: AsyncSession, studio: Studio) -> None:
    """
    Записать событие 'studio.created' в outbox.
    
    Args:
        session: активная AsyncSession (с открытой транзакцией)
        studio: только что созданная Studio (должна иметь id, поэтому
                вызывать после flush())
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = StudioCreatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        studio_id=studio.id,
        name=studio.name,
        description=studio.description,
        address=studio.address,
        phone=studio.phone,
        email=studio.email,
        is_active=studio.is_active,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="studio",
        aggregate_id=str(studio.id),
        event_type="studio.created",
        routing_key="studio.created",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded studio.created in outbox: studio_id=%s name=%s",
        studio.id, studio.name,
    )


async def record_studio_updated(session: AsyncSession, studio: Studio) -> None:
    """
    Записать событие 'studio.updated' в outbox.
    
    Передаём ПОЛНЫЙ снимок состояния студии, а не diff. Consumer
    просто перезаписывает локальную копию, опираясь на occurred_at
    для отбрасывания out-of-order устаревших апдейтов.
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = StudioUpdatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        studio_id=studio.id,
        name=studio.name,
        description=studio.description,
        address=studio.address,
        phone=studio.phone,
        email=studio.email,
        is_active=studio.is_active,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="studio",
        aggregate_id=str(studio.id),
        event_type="studio.updated",
        routing_key="studio.updated",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded studio.updated in outbox: studio_id=%s name=%s is_active=%s",
        studio.id, studio.name, studio.is_active,
    )


async def record_studio_deactivated(
    session: AsyncSession,
    studio_id: int,
) -> None:
    """
    Записать событие 'studio.deactivated' в outbox (soft-delete).
    
    Используется когда студия удаляется - её is_active переводится
    в False, а событие сообщает consumer'ам что её больше не следует
    показывать в активных списках.
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = StudioDeactivatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        studio_id=studio_id,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="studio",
        aggregate_id=str(studio_id),
        event_type="studio.deactivated",
        routing_key="studio.deactivated",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded studio.deactivated in outbox: studio_id=%s",
        studio_id,
    )


# ==================== CLASSROOMS ====================


async def record_classroom_created(
    session: AsyncSession,
    classroom: Classroom,
) -> None:
    """Записать событие 'classroom.created' в outbox."""
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = ClassroomCreatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        classroom_id=classroom.id,
        studio_id=classroom.studio_id,
        name=classroom.name,
        capacity=classroom.capacity,
        description=classroom.description,
        equipment=classroom.equipment,
        floor=classroom.floor,
        room_number=classroom.room_number,
        is_active=classroom.is_active,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="classroom",
        aggregate_id=str(classroom.id),
        event_type="classroom.created",
        routing_key="classroom.created",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded classroom.created in outbox: classroom_id=%s studio_id=%s",
        classroom.id, classroom.studio_id,
    )


async def record_classroom_updated(
    session: AsyncSession,
    classroom: Classroom,
) -> None:
    """Записать событие 'classroom.updated' в outbox."""
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = ClassroomUpdatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        classroom_id=classroom.id,
        studio_id=classroom.studio_id,
        name=classroom.name,
        capacity=classroom.capacity,
        description=classroom.description,
        equipment=classroom.equipment,
        floor=classroom.floor,
        room_number=classroom.room_number,
        is_active=classroom.is_active,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="classroom",
        aggregate_id=str(classroom.id),
        event_type="classroom.updated",
        routing_key="classroom.updated",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded classroom.updated in outbox: classroom_id=%s is_active=%s",
        classroom.id, classroom.is_active,
    )


async def record_classroom_deactivated(
    session: AsyncSession,
    classroom_id: int,
) -> None:
    """Записать событие 'classroom.deactivated' в outbox (soft-delete)."""
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = ClassroomDeactivatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        classroom_id=classroom_id,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="classroom",
        aggregate_id=str(classroom_id),
        event_type="classroom.deactivated",
        routing_key="classroom.deactivated",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded classroom.deactivated in outbox: classroom_id=%s",
        classroom_id,
    )


__all__ = [
    "record_studio_created",
    "record_studio_updated",
    "record_studio_deactivated",
    "record_classroom_created",
    "record_classroom_updated",
    "record_classroom_deactivated",
]