"""
Запись событий в outbox для надёжной публикации в RabbitMQ.

Каждая функция record_* добавляет EventOutbox-запись в текущую сессию,
но НЕ коммитит. Коммит делает вызывающий код вместе с бизнес-данными -
так гарантируется атомарность: либо и занятие, и событие сохранены,
либо ничего.

Воркер publisher_worker.py асинхронно вычитывает unpublished события
и публикует их в RabbitMQ exchange 'schedule_events'.
"""

import logging
from datetime import date, time, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_outbox import EventOutbox

logger = logging.getLogger(__name__)


# ==================== PAYLOADS ====================
# Pydantic-схемы, описывающие точную структуру каждого типа события.
# Это контракт между Schedule (publisher) и consumer'ами (Notifications,
# в будущем Analytics и т.п.). Изменение схемы - breaking change.


class LessonCreatedPayload(BaseModel):
    """Payload события 'lesson.created'."""
    
    model_config = ConfigDict(from_attributes=True)
    
    event_id: str
    occurred_at: str
    
    lesson_id: int
    teacher_id: int
    student_ids: List[int]
    studio_id: int
    classroom_id: Optional[int]
    lesson_date: str       # ISO-формат даты (YYYY-MM-DD)
    start_time: str        # ISO-формат времени (HH:MM:SS)
    end_time: str

class LessonCancelledPayload(BaseModel):
    """Payload события 'lesson.cancelled'."""
    
    model_config = ConfigDict(from_attributes=True)
    
    event_id: str
    occurred_at: str
    
    lesson_id: int
    teacher_id: int
    student_ids: List[int]
    studio_id: int
    lesson_date: str
    start_time: str
    cancellation_reason: Optional[str] = None


class LessonRescheduledPayload(BaseModel):
    """
    Payload события 'lesson.rescheduled'.
    
    Содержит и старое расписание (для текста уведомления "ваше занятие
    перенесено С X на Y"), и новое (чтобы consumer мог обновить свои данные).
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    event_id: str
    occurred_at: str
    
    lesson_id: int
    teacher_id: int
    student_ids: List[int]
    studio_id: int
    
    # Старое расписание (до изменения)
    old_lesson_date: str
    old_start_time: str
    old_end_time: str
    
    # Новое расписание (после изменения)
    new_lesson_date: str
    new_start_time: str
    new_end_time: str



# ==================== RECORD FUNCTIONS ====================


async def record_lesson_created(
    session: AsyncSession,
    *,
    lesson_id: int,
    teacher_id: int,
    student_ids: List[int],
    studio_id: int,
    classroom_id: Optional[int],
    lesson_date: date,
    start_time: time,
    end_time: time,
) -> None:
    """
    Записать событие 'lesson.created' в outbox.
    
    Не коммитит сессию - это делает вызывающий код вместе
    с бизнес-данными (новым Lesson + LessonStudent).
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = LessonCreatedPayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        lesson_id=lesson_id,
        teacher_id=teacher_id,
        student_ids=student_ids,
        studio_id=studio_id,
        classroom_id=classroom_id,
        lesson_date=lesson_date.isoformat(),
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="lesson",
        aggregate_id=str(lesson_id),
        event_type="lesson.created",
        routing_key="lesson.created",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded lesson.created in outbox: lesson_id=%s teacher_id=%s students=%s",
        lesson_id, teacher_id, len(student_ids),
    )

async def record_lesson_cancelled(
    session: AsyncSession,
    *,
    lesson_id: int,
    teacher_id: int,
    student_ids: List[int],
    studio_id: int,
    lesson_date: date,
    start_time: time,
    cancellation_reason: Optional[str] = None,
) -> None:
    """Записать событие 'lesson.cancelled' в outbox."""
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = LessonCancelledPayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        lesson_id=lesson_id,
        teacher_id=teacher_id,
        student_ids=student_ids,
        studio_id=studio_id,
        lesson_date=lesson_date.isoformat(),
        start_time=start_time.isoformat(),
        cancellation_reason=cancellation_reason,
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="lesson",
        aggregate_id=str(lesson_id),
        event_type="lesson.cancelled",
        routing_key="lesson.cancelled",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded lesson.cancelled in outbox: lesson_id=%s students=%s",
        lesson_id, len(student_ids),
    )


async def record_lesson_rescheduled(
    session: AsyncSession,
    *,
    lesson_id: int,
    teacher_id: int,
    student_ids: List[int],
    studio_id: int,
    old_lesson_date: date,
    old_start_time: time,
    old_end_time: time,
    new_lesson_date: date,
    new_start_time: time,
    new_end_time: time,
) -> None:
    """Записать событие 'lesson.rescheduled' в outbox."""
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    
    payload = LessonRescheduledPayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        lesson_id=lesson_id,
        teacher_id=teacher_id,
        student_ids=student_ids,
        studio_id=studio_id,
        old_lesson_date=old_lesson_date.isoformat(),
        old_start_time=old_start_time.isoformat(),
        old_end_time=old_end_time.isoformat(),
        new_lesson_date=new_lesson_date.isoformat(),
        new_start_time=new_start_time.isoformat(),
        new_end_time=new_end_time.isoformat(),
    )
    
    outbox_entry = EventOutbox(
        event_id=event_id,
        aggregate_type="lesson",
        aggregate_id=str(lesson_id),
        event_type="lesson.rescheduled",
        routing_key="lesson.rescheduled",
        payload=payload.model_dump(mode="json"),
    )
    session.add(outbox_entry)
    
    logger.debug(
        "Recorded lesson.rescheduled in outbox: lesson_id=%s students=%s",
        lesson_id, len(student_ids),
    )

__all__ = [
    "LessonCreatedPayload",
    "LessonCancelledPayload",
    "LessonRescheduledPayload",
    "record_lesson_created",
    "record_lesson_cancelled",
    "record_lesson_rescheduled",
]