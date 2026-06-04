"""
Обработчики событий Schedule Service ('schedule_events') для аналитики.

Слушаем три события занятий:
    - lesson.created      -> создаём ряд в lesson_facts (status=scheduled)
    - lesson.cancelled    -> отмечаем отмену (status=cancelled, cancelled_at)
    - lesson.rescheduled  -> обновляем дату занятия, инкрементируем
                             rescheduled_count. НЕ отмена!

Каждый handler следует общему паттерну проекта:
    1. Идемпотентность через processed_events (по event_id).
    2. Применение изменений к проекции lesson_facts.
    3. Запись event_id в processed_events.
    4. Всё в одной транзакции - либо всё, либо ничего.

Out-of-order защита по occurred_at, как в других проекциях.

ВАЖНО - перенос не равен отмене:
    lesson.rescheduled обновляет lesson_date на new_lesson_date и
    increments rescheduled_count, но НЕ трогает status и cancelled_at.
    Так метрика "доля отмен" считает только реальные отмены.

Честное ограничение данных:
    События НЕ несут поля status, а completed/missed вообще не
    публикуются Schedule-сервисом (см. complete_lesson/mark_as_missed -
    там нет record_*). Поэтому аналитика различает только два статуса:
    'scheduled' (создано) и 'cancelled' (отменено). Это задокументировано,
    чтобы дашборд не обещал метрику посещаемости, которой нет в потоке.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal
from app.models.lesson_fact import LessonFact
from app.models.processed_event import ProcessedEvent

logger = logging.getLogger(__name__)


# ==================== ОБЩИЕ ХЕЛПЕРЫ ====================


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


def _parse_dt(raw: Any) -> datetime:
    """Распарсить timestamp из payload в aware datetime (UTC)."""
    if isinstance(raw, datetime):
        value = raw
    else:
        value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _parse_date(raw: Any) -> date:
    """Распарсить дату занятия (ISO YYYY-MM-DD) в date."""
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    return date.fromisoformat(raw)


def _student_count(event: Dict[str, Any]) -> int:
    """Длина student_ids из события, безопасно к отсутствию ключа."""
    ids: List[int] = event.get("student_ids") or []
    return len(ids)


# ==================== HANDLERS ====================


async def handle_lesson_created(event: Dict[str, Any]) -> None:
    """
    Обработать 'lesson.created' - создать проекцию занятия.

    status фиксируется как 'scheduled' (события не несут поля статуса,
    а created по смыслу всегда создаёт запланированное занятие).
    Upsert по id с out-of-order защитой.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_dt(event["occurred_at"])
    now = datetime.now(timezone.utc)

    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(LessonFact).values(
                id=event["lesson_id"],
                teacher_id=event["teacher_id"],
                studio_id=event["studio_id"],
                classroom_id=event.get("classroom_id"),
                status="scheduled",
                lesson_date=_parse_date(event["lesson_date"]),
                student_count=_student_count(event),
                rescheduled_count=0,
                cancellation_reason=None,
                lesson_created_at=occurred_at,
                cancelled_at=None,
                updated_at=occurred_at,
                synced_at=now,
            )
            # При конфликте обновляем "анкетные" поля занятия, но только
            # если событие новее. status/cancelled_at тут НЕ трогаем, чтобы
            # запоздавший created не воскресил уже отменённое занятие.
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "teacher_id": stmt.excluded.teacher_id,
                    "studio_id": stmt.excluded.studio_id,
                    "classroom_id": stmt.excluded.classroom_id,
                    "lesson_date": stmt.excluded.lesson_date,
                    "student_count": stmt.excluded.student_count,
                    "lesson_created_at": stmt.excluded.lesson_created_at,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=LessonFact.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "lesson.created")
            await session.commit()

            logger.info(
                "lesson.created applied: lesson_id=%s event_id=%s",
                event["lesson_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_lesson_cancelled(event: Dict[str, Any]) -> None:
    """
    Обработать 'lesson.cancelled' - отметить отмену занятия.

    Выставляет status='cancelled', cancelled_at, cancellation_reason.
    Если факта ещё нет (cancelled обогнал created) - создаём ряд сразу
    в отменённом состоянии. classroom_id и end_time в payload отмены нет,
    поэтому classroom_id при создании-заготовке будет NULL.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_dt(event["occurred_at"])
    now = datetime.now(timezone.utc)

    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(LessonFact).values(
                id=event["lesson_id"],
                teacher_id=event["teacher_id"],
                studio_id=event["studio_id"],
                classroom_id=None,
                status="cancelled",
                lesson_date=_parse_date(event["lesson_date"]),
                student_count=_student_count(event),
                rescheduled_count=0,
                cancellation_reason=event.get("cancellation_reason"),
                lesson_created_at=occurred_at,
                cancelled_at=occurred_at,
                updated_at=occurred_at,
                synced_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "status": stmt.excluded.status,
                    "cancelled_at": stmt.excluded.cancelled_at,
                    "cancellation_reason": stmt.excluded.cancellation_reason,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=LessonFact.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "lesson.cancelled")
            await session.commit()

            logger.info(
                "lesson.cancelled applied: lesson_id=%s event_id=%s",
                event["lesson_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_lesson_rescheduled(event: Dict[str, Any]) -> None:
    """
    Обработать 'lesson.rescheduled' - перенос занятия.

    ПЕРЕНОС НЕ ОТМЕНА: обновляем lesson_date на new_lesson_date и
    инкрементируем rescheduled_count. status и cancelled_at не трогаем.

    rescheduled_count инкрементируем выражением (текущее значение + 1)
    прямо в UPDATE, чтобы не терять счёт при нескольких переносах.
    Если факта ещё нет - создаём ряд со scheduled и rescheduled_count=1.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_dt(event["occurred_at"])
    now = datetime.now(timezone.utc)

    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(LessonFact).values(
                id=event["lesson_id"],
                teacher_id=event["teacher_id"],
                studio_id=event["studio_id"],
                classroom_id=None,
                status="scheduled",
                lesson_date=_parse_date(event["new_lesson_date"]),
                student_count=_student_count(event),
                rescheduled_count=1,
                cancellation_reason=None,
                lesson_created_at=occurred_at,
                cancelled_at=None,
                updated_at=occurred_at,
                synced_at=now,
            )
            # При конфликте: переносим дату и наращиваем счётчик переносов.
            # rescheduled_count берём из существующего ряда (LessonFact.
            # rescheduled_count + 1), а не из excluded - excluded всегда 1.
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "lesson_date": stmt.excluded.lesson_date,
                    "rescheduled_count": LessonFact.rescheduled_count + 1,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=LessonFact.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "lesson.rescheduled")
            await session.commit()

            logger.info(
                "lesson.rescheduled applied: lesson_id=%s event_id=%s",
                event["lesson_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )