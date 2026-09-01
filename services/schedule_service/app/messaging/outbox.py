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
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID, uuid4

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

# ==================== СОБЫТИЯ ГЕНЕРАЦИИ И ШАБЛОНОВ ====================
#
# Два потока с разным смыслом и разными подписчиками.
#
# generation.*  технический факт "в расписании появились или пропали
#               строки". Слушает только аналитика admin-сервиса.
#               Публикуется ВСЕГДА, включая ежечасное продление
#               горизонта фоновым воркером.
#
# pattern.*     человеческий факт "ученику назначены занятия",
#               "расписание изменилось", "занятия отменены". Слушают
#               рассыльщики - notification и vk_bot. Публикуется ТОЛЬКО
#               при действиях человека над шаблоном. При продлении
#               горизонта - никогда, иначе ученик получал бы сообщение
#               каждый раз, когда горизонт сдвигается на день.
#
# Разделение сделано разными ключами, а не полем-признаком внутри одного
# события: рассыльщик просто не подписан на технический поток и не
# обязан знать, какие значения признака его касаются.
#
# ВАЖНО ПРО ИМЕНА КЛЮЧЕЙ.
# Очереди notification, vk_bot и admin исторически привязаны к 'lesson.*'.
# Ключи ниже начинаются со слов 'generation' и 'pattern' именно поэтому:
# под эту привязку они не попадают ни при каких условиях. Если кто-то
# решит "исправить" первое слово на 'lesson', маршрутизация сломается
# молча: технические события посыплются рассыльщикам, и ученик получит
# по сообщению на каждое созданное занятие - ровно та беда, ради которой
# всё это и разделялось.


# Почему были удалены занятия. Строка уходит в payload и нужна при
# разборе расхождений в аналитике: одно дело плановая пересборка
# расписания, другое - ручной откат прогона.
DELETION_REASON_PATTERN_UPDATED = "pattern_updated"
DELETION_REASON_PATTERN_DELETED = "pattern_deleted"
DELETION_REASON_BATCH_ROLLED_BACK = "batch_rolled_back"

# Сколько ближайших дат класть в человеческое событие. Ученику нужен
# ориентир "когда первое занятие", а не весь список на две недели.
UPCOMING_DATES_LIMIT = 5


class GeneratedLessonItem(BaseModel):
    """Одно созданное занятие внутри пакетного события."""

    model_config = ConfigDict(from_attributes=True)

    lesson_id: int
    slot_id: Optional[int]
    lesson_date: str       # ISO YYYY-MM-DD
    start_time: str        # ISO HH:MM:SS
    end_time: str
    classroom_id: Optional[int]


class GenerationLessonsCreatedPayload(BaseModel):
    """
    Payload события 'generation.lessons_created'.

    Пакетное по своей природе: один прогон генерации - одно событие,
    сколько бы занятий он ни создал. Потребитель разворачивает пакет
    в отдельные строки проекции сам.

    Такая форма выбрана не ради экономии сообщений, а ради смысла:
    "создалось тридцать занятий по одному шаблону" - это один факт,
    а не тридцать независимых.
    """

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    occurred_at: str

    pattern_id: int
    batch_id: str
    studio_id: int
    teacher_id: int
    student_ids: List[int]
    lessons: List[GeneratedLessonItem]


class GenerationLessonsDeletedPayload(BaseModel):
    """
    Payload события 'generation.lessons_deleted'.

    Обратная половина к created. Без неё аналитическая проекция навсегда
    остаётся со строками о занятиях, которых больше нет в расписании:
    правка шаблона удаляет будущие занятия и создаёт новые, и без этого
    события admin видел бы только вторую половину операции.

    pattern_id и batch_id необязательны: откат прогона знает batch_id,
    но не знает шаблон, а удаление шаблона - наоборот.
    """

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    occurred_at: str

    lesson_ids: List[int]
    reason: str
    pattern_id: Optional[int] = None
    batch_id: Optional[str] = None


class PatternSlotItem(BaseModel):
    """Один слот шаблона в человеческом событии."""

    model_config = ConfigDict(from_attributes=True)

    day_of_week: int
    day_name: str
    start_time: str
    end_time: str
    classroom_id: Optional[int]


class PatternSchedulePayload(BaseModel):
    """
    Payload событий 'pattern.assigned' и 'pattern.changed'.

    Один класс на два ключа: содержимое одинаковое, различается только
    адресат и текст сообщения, а это решает потребитель по routing key.

    schedule_text собирается здесь, а не у каждого рассыльщика: иначе
    notification и vk_bot независимо реализовали бы одно и то же
    форматирование и рано или поздно разошлись бы в словах. Структурные
    слоты тоже отдаются - они понадобятся напоминаниям, которым нужен
    не текст, а данные.

    previous_schedule_text заполнен только у 'pattern.changed': чтобы
    сказать "было вторник 18:00, стало четверг 19:30", нужны обе половины.
    """

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    occurred_at: str

    pattern_id: int
    studio_id: int
    teacher_id: int
    student_ids: List[int]

    slots: List[PatternSlotItem]
    schedule_text: str
    previous_schedule_text: Optional[str] = None

    upcoming_dates: List[str]
    valid_until: Optional[str] = None


class PatternUnassignedPayload(BaseModel):
    """
    Payload события 'pattern.unassigned'.

    Ученик снят с регулярных занятий. Расписание здесь только прошлое:
    будущего у этого ученика по этому шаблону больше нет.
    """

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    occurred_at: str

    pattern_id: int
    studio_id: int
    teacher_id: int
    student_ids: List[int]
    previous_schedule_text: str


def _format_schedule_text(slots: Sequence[PatternSlotItem]) -> str:
    """
    Слоты одной строкой: "вторник 18:00, четверг 19:30".

    Порядок - по дню недели, затем по времени, независимо от того,
    в каком порядке слоты пришли из формы. Ученик должен читать
    расписание в том же порядке, в каком проживает неделю.
    """
    ordered = sorted(slots, key=lambda item: (item.day_of_week, item.start_time))
    return ", ".join(
        f"{item.day_name} {item.start_time[:5]}" for item in ordered
    )


async def record_generation_lessons_created(
    session: AsyncSession,
    *,
    pattern_id: int,
    batch_id: UUID,
    studio_id: int,
    teacher_id: int,
    student_ids: List[int],
    lessons: Sequence[GeneratedLessonItem],
) -> None:
    """
    Записать событие 'generation.lessons_created' в outbox.

    Пустой список занятий события не порождает: рассказывать не о чем.
    Проверка стоит здесь, а не у вызывающего, чтобы её нельзя было
    забыть в новом месте вызова.

    Не коммитит.
    """
    if not lessons:
        return

    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = GenerationLessonsCreatedPayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        pattern_id=pattern_id,
        batch_id=str(batch_id),
        studio_id=studio_id,
        teacher_id=teacher_id,
        student_ids=list(student_ids),
        lessons=list(lessons),
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="recurring_pattern",
            aggregate_id=str(pattern_id),
            event_type="generation.lessons_created",
            routing_key="generation.lessons_created",
            payload=payload.model_dump(mode="json"),
        )
    )

    logger.debug(
        "Recorded generation.lessons_created in outbox: pattern=%s batch=%s lessons=%s",
        pattern_id, batch_id, len(lessons),
    )


async def record_generation_lessons_deleted(
    session: AsyncSession,
    *,
    lesson_ids: List[int],
    reason: str,
    pattern_id: Optional[int] = None,
    batch_id: Optional[UUID] = None,
) -> None:
    """
    Записать событие 'generation.lessons_deleted' в outbox.

    Не коммитит.
    """
    if not lesson_ids:
        return

    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = GenerationLessonsDeletedPayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        lesson_ids=list(lesson_ids),
        reason=reason,
        pattern_id=pattern_id,
        batch_id=str(batch_id) if batch_id is not None else None,
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="recurring_pattern" if pattern_id else "generation_batch",
            aggregate_id=str(pattern_id if pattern_id else batch_id),
            event_type="generation.lessons_deleted",
            routing_key="generation.lessons_deleted",
            payload=payload.model_dump(mode="json"),
        )
    )

    logger.debug(
        "Recorded generation.lessons_deleted in outbox: pattern=%s batch=%s lessons=%s reason=%s",
        pattern_id, batch_id, len(lesson_ids), reason,
    )


async def _record_pattern_schedule_event(
    session: AsyncSession,
    *,
    routing_key: str,
    pattern_id: int,
    studio_id: int,
    teacher_id: int,
    student_ids: List[int],
    slots: Sequence[PatternSlotItem],
    upcoming_dates: Sequence[date],
    valid_until: Optional[date],
    previous_slots: Optional[Sequence[PatternSlotItem]] = None,
) -> None:
    """Общее тело для 'pattern.assigned' и 'pattern.changed'."""
    if not student_ids or not slots:
        return

    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = PatternSchedulePayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        pattern_id=pattern_id,
        studio_id=studio_id,
        teacher_id=teacher_id,
        student_ids=list(student_ids),
        slots=list(slots),
        schedule_text=_format_schedule_text(slots),
        previous_schedule_text=(
            _format_schedule_text(previous_slots) if previous_slots else None
        ),
        upcoming_dates=[
            item.isoformat() for item in sorted(upcoming_dates)[:UPCOMING_DATES_LIMIT]
        ],
        valid_until=valid_until.isoformat() if valid_until else None,
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="recurring_pattern",
            aggregate_id=str(pattern_id),
            event_type=routing_key,
            routing_key=routing_key,
            payload=payload.model_dump(mode="json"),
        )
    )

    logger.debug(
        "Recorded %s in outbox: pattern=%s students=%s",
        routing_key, pattern_id, len(student_ids),
    )


async def record_pattern_assigned(
    session: AsyncSession,
    *,
    pattern_id: int,
    studio_id: int,
    teacher_id: int,
    student_ids: List[int],
    slots: Sequence[PatternSlotItem],
    upcoming_dates: Sequence[date],
    valid_until: Optional[date] = None,
) -> None:
    """
    Записать событие 'pattern.assigned' в outbox.

    Адресат - ученики, которым регулярные занятия назначены впервые:
    при создании шаблона это все, при правке - только добавленные.

    Не коммитит.
    """
    await _record_pattern_schedule_event(
        session,
        routing_key="pattern.assigned",
        pattern_id=pattern_id,
        studio_id=studio_id,
        teacher_id=teacher_id,
        student_ids=student_ids,
        slots=slots,
        upcoming_dates=upcoming_dates,
        valid_until=valid_until,
    )


async def record_pattern_changed(
    session: AsyncSession,
    *,
    pattern_id: int,
    studio_id: int,
    teacher_id: int,
    student_ids: List[int],
    slots: Sequence[PatternSlotItem],
    previous_slots: Sequence[PatternSlotItem],
    upcoming_dates: Sequence[date],
    valid_until: Optional[date] = None,
) -> None:
    """
    Записать событие 'pattern.changed' в outbox.

    Адресат - ученики, которые были в шаблоне и остались: только им
    имеет смысл говорить "было так, стало эдак".

    Не коммитит.
    """
    await _record_pattern_schedule_event(
        session,
        routing_key="pattern.changed",
        pattern_id=pattern_id,
        studio_id=studio_id,
        teacher_id=teacher_id,
        student_ids=student_ids,
        slots=slots,
        upcoming_dates=upcoming_dates,
        valid_until=valid_until,
        previous_slots=previous_slots,
    )


async def record_pattern_unassigned(
    session: AsyncSession,
    *,
    pattern_id: int,
    studio_id: int,
    teacher_id: int,
    student_ids: List[int],
    previous_slots: Sequence[PatternSlotItem],
) -> None:
    """
    Записать событие 'pattern.unassigned' в outbox.

    Адресат - ученики, снятые с шаблона. Их будущие занятия к этому
    моменту уже удалены, поэтому сообщение - единственный способ
    об этом узнать.

    Не коммитит.
    """
    if not student_ids:
        return

    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = PatternUnassignedPayload(
        event_id=str(event_id),
        occurred_at=occurred_at.isoformat(),
        pattern_id=pattern_id,
        studio_id=studio_id,
        teacher_id=teacher_id,
        student_ids=list(student_ids),
        previous_schedule_text=_format_schedule_text(previous_slots),
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="recurring_pattern",
            aggregate_id=str(pattern_id),
            event_type="pattern.unassigned",
            routing_key="pattern.unassigned",
            payload=payload.model_dump(mode="json"),
        )
    )

    logger.debug(
        "Recorded pattern.unassigned in outbox: pattern=%s students=%s",
        pattern_id, len(student_ids),
    )

__all__ = [
    "LessonCreatedPayload",
    "LessonCancelledPayload",
    "LessonRescheduledPayload",
    "record_lesson_created",
    "record_lesson_cancelled",
    "record_lesson_rescheduled",
]