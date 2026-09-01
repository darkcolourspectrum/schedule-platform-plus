"""
Обработчики событий из RabbitMQ.

Каждый handler:
    1. Проверяет идемпотентность через таблицу processed_events.
       Если event_id уже обработан - пропускает.
    2. Создаёт уведомления для всех затронутых студентов.
    3. Записывает event_id в processed_events.
    4. Всё в одной транзакции - либо все уведомления и запись
       processed_events, либо ничего.

Новая схема payload (после перехода Schedule на outbox):
    - event_id: UUID для идемпотентности
    - occurred_at: ISO timestamp когда событие произошло
    - lesson_id, teacher_id, student_ids, studio_id и т.п.
    
event_type не передаётся в payload - он определяется через routing_key
в consumer (см. consumer.py HANDLERS dict).
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AsyncSessionLocal
from app.models.processed_event import ProcessedEvent
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def _is_already_processed(session: AsyncSession, event_id: UUID) -> bool:
    """Проверить, было ли событие уже обработано."""
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


def _format_time(time_str: str) -> str:
    """Преобразовать ISO время '14:30:00' в читаемое '14:30'."""
    return time_str[:5] if time_str else ""


async def handle_lesson_created(event: Dict[str, Any]) -> None:
    """
    Обработать событие 'lesson.created'.
    Создаёт уведомления для всех учеников нового занятия.
    """
    event_id = UUID(event["event_id"])
    student_ids = event.get("student_ids", [])
    
    if not student_ids:
        logger.info("lesson.created has no students, skipping: lesson_id=%s",
                    event.get("lesson_id"))
        return
    
    lesson_id = event["lesson_id"]
    teacher_id = event["teacher_id"]
    studio_id = event["studio_id"]
    lesson_date = event["lesson_date"]
    start_time = event["start_time"]
    
    title = "Новое занятие"
    message = f"Преподаватель назначил вам занятие {lesson_date} в {_format_time(start_time)}"
    
    payload = {
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "studio_id": studio_id,
        "lesson_date": lesson_date,
        "start_time": start_time,
    }
    
    async with AsyncSessionLocal() as db:
        try:
            if await _is_already_processed(db, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            service = NotificationService(db)
            for student_id in student_ids:
                await service.create_notification(
                    user_id=student_id,
                    type="lesson_created",
                    title=title,
                    message=message,
                    payload=payload,
                )
            
            await _mark_processed(db, event_id, "lesson.created")
            await db.commit()
            
            logger.info(
                "lesson.created processed: lesson_id=%s notifications=%d event_id=%s",
                lesson_id, len(student_ids), event_id,
            )
        except IntegrityError as exc:
            await db.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)


async def handle_lesson_cancelled(event: Dict[str, Any]) -> None:
    """
    Обработать событие 'lesson.cancelled'.
    Создаёт уведомления об отмене для всех учеников.
    """
    event_id = UUID(event["event_id"])
    student_ids = event.get("student_ids", [])
    
    if not student_ids:
        logger.info("lesson.cancelled has no students, skipping: lesson_id=%s",
                    event.get("lesson_id"))
        return
    
    lesson_id = event["lesson_id"]
    teacher_id = event["teacher_id"]
    studio_id = event["studio_id"]
    lesson_date = event["lesson_date"]
    start_time = event["start_time"]
    cancellation_reason = event.get("cancellation_reason")
    
    title = "Занятие отменено"
    base_msg = f"Занятие {lesson_date} в {_format_time(start_time)} отменено"
    message = f"{base_msg}. Причина: {cancellation_reason}" if cancellation_reason else base_msg
    
    payload = {
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "studio_id": studio_id,
        "lesson_date": lesson_date,
        "start_time": start_time,
        "cancellation_reason": cancellation_reason,
    }
    
    async with AsyncSessionLocal() as db:
        try:
            if await _is_already_processed(db, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            service = NotificationService(db)
            for student_id in student_ids:
                await service.create_notification(
                    user_id=student_id,
                    type="lesson_cancelled",
                    title=title,
                    message=message,
                    payload=payload,
                )
            
            await _mark_processed(db, event_id, "lesson.cancelled")
            await db.commit()
            
            logger.info(
                "lesson.cancelled processed: lesson_id=%s notifications=%d event_id=%s",
                lesson_id, len(student_ids), event_id,
            )
        except IntegrityError as exc:
            await db.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)


async def handle_lesson_rescheduled(event: Dict[str, Any]) -> None:
    """
    Обработать событие 'lesson.rescheduled'.
    Создаёт уведомления о переносе для всех учеников.
    """
    event_id = UUID(event["event_id"])
    student_ids = event.get("student_ids", [])
    
    if not student_ids:
        logger.info("lesson.rescheduled has no students, skipping: lesson_id=%s",
                    event.get("lesson_id"))
        return
    
    lesson_id = event["lesson_id"]
    teacher_id = event["teacher_id"]
    studio_id = event["studio_id"]
    old_date = event["old_lesson_date"]
    old_start = event["old_start_time"]
    new_date = event["new_lesson_date"]
    new_start = event["new_start_time"]
    
    title = "Занятие перенесено"
    message = (
        f"Занятие перенесено с {old_date} {_format_time(old_start)} "
        f"на {new_date} {_format_time(new_start)}"
    )
    
    payload = {
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "studio_id": studio_id,
        "old_lesson_date": old_date,
        "old_start_time": old_start,
        "new_lesson_date": new_date,
        "new_start_time": new_start,
    }
    
    async with AsyncSessionLocal() as db:
        try:
            if await _is_already_processed(db, event_id):
                logger.debug("Event already processed, skipping: event_id=%s", event_id)
                return
            
            service = NotificationService(db)
            for student_id in student_ids:
                await service.create_notification(
                    user_id=student_id,
                    type="lesson_rescheduled",
                    title=title,
                    message=message,
                    payload=payload,
                )
            
            await _mark_processed(db, event_id, "lesson.rescheduled")
            await db.commit()
            
            logger.info(
                "lesson.rescheduled processed: lesson_id=%s notifications=%d event_id=%s",
                lesson_id, len(student_ids), event_id,
            )
        except IntegrityError as exc:
            await db.rollback()
            logger.debug("Event processed concurrently, skipping: event_id=%s err=%s",
                         event_id, exc)

# ==================== СОБЫТИЯ ШАБЛОНОВ ====================
#
# Три события вместо одного, потому что это три разных факта с разными
# адресатами. При одном сохранении формы админом могут случиться все три
# сразу: расписание сдвинули, кого-то добавили, кого-то сняли.
#
# Разделение сделано на стороне отправителя: routing key определяет, кому
# и о чём пишем, а handler'у остаётся только текст. Это намеренно -
# фильтрация "а это событие про меня?" внутри потребителя быстро
# превращается в набор условий, которые никто не решается тронуть.
#
# Технический поток generation.* сюда не приходит вовсе: очередь
# привязана к 'lesson.*' и 'pattern.*'. Иначе ученик получал бы
# сообщение каждый раз, когда фоновый воркер продлевает горизонт.

_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _format_date(iso_date: str) -> str:
    """ISO-дату '2026-09-03' в человеческое '3 сентября'."""
    try:
        _, month, day = (int(part) for part in iso_date.split("-"))
        return f"{day} {_MONTHS_GENITIVE[month - 1]}"
    except (ValueError, IndexError):
        return iso_date


def _upcoming_hint(dates: Optional[List[str]]) -> str:
    """
    Хвост сообщения с ближайшей датой.

    Расписания словами мало: "занятия по вторникам" не отвечает на вопрос
    "а когда первое". Если дат нет - молчим, вместо того чтобы обещать
    занятие, которого в базе не оказалось.
    """
    if not dates:
        return ""
    return f" Ближайшее занятие - {_format_date(dates[0])}."


async def _notify_students(
    *,
    event_id: UUID,
    event_type: str,
    notification_type: str,
    student_ids: List[int],
    title: str,
    message: str,
    payload: Dict[str, Any],
) -> None:
    """
    Создать одинаковое уведомление каждому ученику из списка.

    Общее тело для трёх событий шаблона: у них различаются только тексты,
    а идемпотентность, транзакция и логирование одни и те же.
    """
    async with AsyncSessionLocal() as db:
        try:
            if await _is_already_processed(db, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            service = NotificationService(db)
            for student_id in student_ids:
                await service.create_notification(
                    user_id=student_id,
                    type=notification_type,
                    title=title,
                    message=message,
                    payload=payload,
                )

            await _mark_processed(db, event_id, event_type)
            await db.commit()

            logger.info(
                "%s processed: pattern_id=%s notifications=%d event_id=%s",
                event_type, payload.get("pattern_id"), len(student_ids), event_id,
            )
        except IntegrityError as exc:
            await db.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


def _pattern_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Общая часть payload уведомления - для перехода по клику."""
    return {
        "pattern_id": event.get("pattern_id"),
        "studio_id": event.get("studio_id"),
        "teacher_id": event.get("teacher_id"),
        "schedule_text": event.get("schedule_text"),
        "upcoming_dates": event.get("upcoming_dates") or [],
    }


async def handle_pattern_assigned(event: Dict[str, Any]) -> None:
    """
    Обработать 'pattern.assigned' - ученику назначили регулярные занятия.

    Адресат - те, для кого расписание новое: все ученики при создании
    шаблона и только добавленные при правке.
    """
    student_ids: List[int] = event.get("student_ids") or []
    if not student_ids:
        return

    schedule_text = event.get("schedule_text") or ""

    await _notify_students(
        event_id=UUID(str(event["event_id"])),
        event_type="pattern.assigned",
        notification_type="pattern_assigned",
        student_ids=student_ids,
        title="Регулярные занятия",
        message=(
            f"Вам назначены регулярные занятия: {schedule_text}."
            f"{_upcoming_hint(event.get('upcoming_dates'))}"
        ),
        payload=_pattern_payload(event),
    )


async def handle_pattern_changed(event: Dict[str, Any]) -> None:
    """
    Обработать 'pattern.changed' - расписание регулярных занятий сдвинулось.

    Адресат - те, кто был в шаблоне и остался: только им осмысленно
    говорить "было так, стало эдак".
    """
    student_ids: List[int] = event.get("student_ids") or []
    if not student_ids:
        return

    schedule_text = event.get("schedule_text") or ""
    previous = event.get("previous_schedule_text")

    message = f"Ваши регулярные занятия теперь проходят так: {schedule_text}."
    if previous:
        message += f" Раньше было: {previous}."
    message += _upcoming_hint(event.get("upcoming_dates"))

    await _notify_students(
        event_id=UUID(str(event["event_id"])),
        event_type="pattern.changed",
        notification_type="pattern_changed",
        student_ids=student_ids,
        title="Расписание изменилось",
        message=message,
        payload=_pattern_payload(event),
    )


async def handle_pattern_unassigned(event: Dict[str, Any]) -> None:
    """
    Обработать 'pattern.unassigned' - ученика сняли с регулярных занятий.

    Его будущие занятия к этому моменту уже удалены из расписания,
    поэтому уведомление - единственный способ об этом узнать.
    """
    student_ids: List[int] = event.get("student_ids") or []
    if not student_ids:
        return

    previous = event.get("previous_schedule_text") or ""

    await _notify_students(
        event_id=UUID(str(event["event_id"])),
        event_type="pattern.unassigned",
        notification_type="pattern_unassigned",
        student_ids=student_ids,
        title="Регулярные занятия отменены",
        message=(
            f"Занятия по расписанию {previous} больше не проводятся. "
            f"Будущие занятия убраны из вашего расписания."
        ),
        payload=_pattern_payload(event),
    )
