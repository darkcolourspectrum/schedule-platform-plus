"""
Сервис занятий.

Переписан целиком. Что изменилось по существу:

    1. Конфликты. Проверялся только кабинет и только если он задан.
       Теперь через ConflictService проверяются все три ресурса -
       кабинет, преподаватель, ученики - на любом пути, включая
       восстановление отменённого занятия.

    2. Время. Локальная копия _calculate_end_time молча превращала
       23:30 плюс час в 00:30 и ломала все сравнения интервалов.
       Расчёт переехал в app/domain/recurrence.py, единый для всего
       сервиса, и честно отклоняет переход через полночь.

    3. Статусы. Таблица переходов существовала, но не вызывалась ни
       из одного метода: отменённое занятие можно было отметить
       проведённым. Теперь проверка стоит на каждом переходе.

    4. Посещаемость. Раньше attendance_status учеников оставался
       'scheduled' навсегда, а API отдавал захардкоженные значения.
       Теперь статус посещения реально сохраняется и читается.

    5. Ручные правки. Занятие, изменённое человеком, помечается
       флагом is_manually_modified, и перегенерация из шаблона его
       больше не трогает.

    6. История. Проведённые, пропущенные и прошедшие занятия нельзя
       удалить - только отменить.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidLessonStatusException,
    LessonImmutableException,
    LessonNotFoundException,
)
from app.domain.conflicts import ConflictKind, LessonCandidate
from app.domain.recurrence import (
    calculate_end_time,
    duration_minutes_between,
    today_in_studio_tz,
)
from app.messaging import (
    record_lesson_cancelled,
    record_lesson_created,
    record_lesson_rescheduled,
)
from app.models.lesson import Lesson
from app.models.lesson_student import LessonStudent
from app.repositories.lesson_repository import LessonRepository
from app.schemas.lesson import LessonCreate, LessonUpdate
from app.services.conflict_service import ConflictService

logger = logging.getLogger(__name__)


# Разрешённые переходы статусов.
#
# Переходы обратно в scheduled оставлены намеренно: преподаватель может
# ошибиться кнопкой, и отметка "проведено" не должна быть необратимой.
# Из этих переходов проверки конфликтов требует только cancelled ->
# scheduled: отменённое занятие освобождает слот (оно исключено из
# EXCLUDE-констрейнтов), и за время отмены слот могли занять.
# Проведённое и пропущенное слот не освобождают, поэтому их возврат
# в scheduled ничего не бронирует заново.
ALLOWED_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "scheduled": ["completed", "cancelled", "missed"],
    "completed": ["scheduled", "missed"],
    "missed": ["scheduled", "completed"],
    "cancelled": ["scheduled"],
}

# Статус занятия -> статус посещения учеников по умолчанию.
ATTENDANCE_BY_STATUS = {
    "scheduled": "scheduled",
    "completed": "attended",
    "cancelled": "cancelled",
    "missed": "missed",
}

CONFLICT_EXCEPTIONS = {
    ConflictKind.CLASSROOM: "Кабинет занят другим занятием в это время",
    ConflictKind.TEACHER: "У преподавателя уже есть занятие в это время",
    ConflictKind.STUDENT: "Ученик уже занят на другом занятии в это время",
}


class LessonService:
    """Создание, изменение и статусы занятий."""

    def __init__(
        self,
        lesson_repo: LessonRepository,
        conflict_service: ConflictService,
        db: AsyncSession,
    ):
        self.lesson_repo = lesson_repo
        self.conflict_service = conflict_service
        self.db = db

    # ==================== ЧТЕНИЕ ====================

    async def get_lesson(self, lesson_id: int) -> Lesson:
        lesson = await self.lesson_repo.get_by_id(lesson_id)
        if not lesson:
            raise LessonNotFoundException(lesson_id)
        return lesson

    async def get_lesson_student_ids(self, lesson_id: int) -> List[int]:
        return await self.lesson_repo.get_student_ids(lesson_id)

    async def get_lesson_students(self, lesson_id: int) -> List[LessonStudent]:
        """Ученики занятия с настоящим статусом посещения."""
        return await self.lesson_repo.get_students(lesson_id)

    async def get_lessons_by_studio(
        self, studio_id: int, from_date: date, to_date: date
    ) -> List[Lesson]:
        return await self.lesson_repo.get_by_studio(studio_id, from_date, to_date)

    async def get_lessons_by_teacher(
        self, teacher_id: int, from_date: date, to_date: date
    ) -> List[Lesson]:
        return await self.lesson_repo.get_by_teacher(teacher_id, from_date, to_date)

    async def get_lessons_by_student(
        self, student_id: int, from_date: date, to_date: date
    ) -> List[Lesson]:
        return await self.lesson_repo.get_by_student(student_id, from_date, to_date)

    # ==================== СОЗДАНИЕ ====================

    async def create_lesson(self, data: LessonCreate) -> Lesson:
        """
        Создать разовое занятие.

        Не коммитит: занятие, ученики и запись в outbox сохраняются одной
        транзакцией на уровне зависимости FastAPI.
        """
        # Бросит LessonCrossesMidnightError, если занятие не влезает
        # в сутки. Обработчик в main.py превратит это в 400.
        end_time = calculate_end_time(data.start_time, data.duration_minutes)

        await self._assert_no_conflicts(
            LessonCandidate(
                lesson_date=data.lesson_date,
                start_time=data.start_time,
                end_time=end_time,
                teacher_id=data.teacher_id,
                classroom_id=data.classroom_id,
                student_ids=tuple(data.student_ids),
            )
        )

        lesson = Lesson(
            studio_id=data.studio_id,
            teacher_id=data.teacher_id,
            classroom_id=data.classroom_id,
            recurring_pattern_id=None,
            recurring_pattern_slot_id=None,
            lesson_date=data.lesson_date,
            start_time=data.start_time,
            end_time=end_time,
            status="scheduled",
            is_manually_modified=False,
            notes=data.notes,
        )

        lesson = await self.lesson_repo.create(lesson)

        for student_id in data.student_ids:
            await self.lesson_repo.add_student(lesson.id, student_id)

        await record_lesson_created(
            self.db,
            lesson_id=lesson.id,
            teacher_id=lesson.teacher_id,
            student_ids=list(data.student_ids),
            studio_id=lesson.studio_id,
            classroom_id=lesson.classroom_id,
            lesson_date=lesson.lesson_date,
            start_time=lesson.start_time,
            end_time=lesson.end_time,
        )

        logger.info("Created lesson %s", lesson.id)
        return lesson

    # ==================== ИЗМЕНЕНИЕ ====================

    async def update_lesson(self, lesson_id: int, data: LessonUpdate) -> Lesson:
        """
        Изменить расписание, кабинет или заметки занятия.

        Занятие, изменённое здесь, получает флаг is_manually_modified.
        С этого момента перегенерация из шаблона его не трогает: правка
        шаблона не должна стирать индивидуальные исключения, которые
        админ сделал руками.
        """
        lesson = await self.get_lesson(lesson_id)

        if lesson.status in ("completed", "missed"):
            raise LessonImmutableException(
                "Нельзя изменить расписание проведённого или пропущенного "
                "занятия. Сначала верните его в статус запланированного"
            )

        old_date = lesson.lesson_date
        old_start = lesson.start_time
        old_end = lesson.end_time
        old_classroom = lesson.classroom_id

        new_date = data.lesson_date or old_date
        new_start = data.start_time or old_start
        new_classroom = (
            data.classroom_id if data.classroom_id is not None else old_classroom
        )

        if data.duration_minutes is not None:
            new_end = calculate_end_time(new_start, data.duration_minutes)
        elif data.start_time is not None:
            # Время начала сдвинули, длительность оставили прежней.
            new_end = calculate_end_time(
                new_start, duration_minutes_between(old_start, old_end)
            )
        else:
            new_end = old_end

        schedule_changed = (
            new_date != old_date
            or new_start != old_start
            or new_end != old_end
            or new_classroom != old_classroom
        )

        if schedule_changed:
            student_ids = await self.lesson_repo.get_student_ids(lesson_id)
            await self._assert_no_conflicts(
                LessonCandidate(
                    lesson_date=new_date,
                    start_time=new_start,
                    end_time=new_end,
                    teacher_id=lesson.teacher_id,
                    classroom_id=new_classroom,
                    student_ids=tuple(student_ids),
                ),
                exclude_lesson_id=lesson_id,
            )

        lesson.lesson_date = new_date
        lesson.start_time = new_start
        lesson.end_time = new_end
        lesson.classroom_id = new_classroom

        if data.notes is not None:
            lesson.notes = data.notes

        if schedule_changed:
            lesson.is_manually_modified = True

        lesson = await self.lesson_repo.update_obj(lesson)
        logger.info(
            "Updated lesson %s (schedule_changed=%s)", lesson_id, schedule_changed
        )

        # Уведомляем только о переносе во времени. Смена кабинета или
        # заметки ученику не интересна.
        time_changed = (
            lesson.lesson_date != old_date
            or lesson.start_time != old_start
            or lesson.end_time != old_end
        )

        if time_changed:
            student_ids = await self.lesson_repo.get_student_ids(lesson_id)
            await record_lesson_rescheduled(
                self.db,
                lesson_id=lesson.id,
                teacher_id=lesson.teacher_id,
                student_ids=student_ids,
                studio_id=lesson.studio_id,
                old_lesson_date=old_date,
                old_start_time=old_start,
                old_end_time=old_end,
                new_lesson_date=lesson.lesson_date,
                new_start_time=lesson.start_time,
                new_end_time=lesson.end_time,
            )

        return lesson

    # ==================== СТАТУСЫ ====================

    async def cancel_lesson(
        self, lesson_id: int, reason: Optional[str] = None
    ) -> Lesson:
        """
        Отменить занятие.

        Отмена освобождает кабинет и преподавателя: отменённые занятия
        исключены из проверки конфликтов и из EXCLUDE-констрейнтов.
        """
        lesson = await self.get_lesson(lesson_id)

        if lesson.status == "cancelled":
            return lesson

        self._assert_transition_allowed(lesson.status, "cancelled")

        lesson.status = "cancelled"
        if reason:
            lesson.cancellation_reason = reason

        lesson = await self.lesson_repo.update_obj(lesson)
        await self.lesson_repo.set_attendance_for_all(lesson_id, "cancelled")

        student_ids = await self.lesson_repo.get_student_ids(lesson_id)
        await record_lesson_cancelled(
            self.db,
            lesson_id=lesson.id,
            teacher_id=lesson.teacher_id,
            student_ids=student_ids,
            studio_id=lesson.studio_id,
            lesson_date=lesson.lesson_date,
            start_time=lesson.start_time,
            cancellation_reason=reason,
        )

        logger.info("Cancelled lesson %s", lesson_id)
        return lesson

    async def restore_lesson(self, lesson_id: int) -> Lesson:
        """
        Вернуть отменённое занятие в расписание.

        Единственный переход, требующий проверки конфликтов: пока занятие
        было отменено, его слот считался свободным, и время могли занять.
        Раньше этот путь не проверял ничего и создавал двойное
        бронирование.
        """
        lesson = await self.get_lesson(lesson_id)

        if lesson.status == "scheduled":
            return lesson

        self._assert_transition_allowed(lesson.status, "scheduled")

        if lesson.status == "cancelled":
            student_ids = await self.lesson_repo.get_student_ids(lesson_id)
            await self._assert_no_conflicts(
                LessonCandidate(
                    lesson_date=lesson.lesson_date,
                    start_time=lesson.start_time,
                    end_time=lesson.end_time,
                    teacher_id=lesson.teacher_id,
                    classroom_id=lesson.classroom_id,
                    student_ids=tuple(student_ids),
                ),
                exclude_lesson_id=lesson_id,
            )

        lesson.status = "scheduled"
        lesson.cancellation_reason = None

        lesson = await self.lesson_repo.update_obj(lesson)
        await self.lesson_repo.set_attendance_for_all(lesson_id, "scheduled")

        logger.info("Restored lesson %s to scheduled", lesson_id)
        return lesson

    async def complete_lesson(
        self,
        lesson_id: int,
        attendance: Optional[Dict[int, str]] = None,
    ) -> Lesson:
        """
        Отметить занятие проведённым.

        Args:
            attendance: посещаемость по ученикам, {student_id: статус}.
                Не указана - все считаются присутствовавшими.

        Раздельная посещаемость нужна, потому что "занятие не состоялось"
        и "один ученик не пришёл" - разные события. Для группового занятия
        второе не должно отменять первое.
        """
        lesson = await self.get_lesson(lesson_id)
        self._assert_transition_allowed(lesson.status, "completed")

        lesson.status = "completed"
        lesson = await self.lesson_repo.update_obj(lesson)

        if attendance:
            await self.lesson_repo.set_attendance_bulk(lesson_id, attendance)
        else:
            await self.lesson_repo.set_attendance_for_all(lesson_id, "attended")

        logger.info("Completed lesson %s", lesson_id)
        return lesson

    async def mark_as_missed(self, lesson_id: int) -> Lesson:
        """Отметить занятие как несостоявшееся по вине ученика."""
        lesson = await self.get_lesson(lesson_id)
        self._assert_transition_allowed(lesson.status, "missed")

        lesson.status = "missed"
        lesson = await self.lesson_repo.update_obj(lesson)
        await self.lesson_repo.set_attendance_for_all(lesson_id, "missed")

        logger.info("Marked lesson %s as missed", lesson_id)
        return lesson

    # ==================== УДАЛЕНИЕ ====================

    async def delete_lesson(self, lesson_id: int) -> bool:
        """
        Удалить занятие.

        Удалить можно только запланированное занятие в будущем. Всё
        остальное - это уже история: она нужна аналитике, отчётам и
        разбору спорных ситуаций. Для несостоявшегося занятия правильное
        действие - отмена, а не удаление.
        """
        lesson = await self.get_lesson(lesson_id)

        if lesson.status in ("completed", "missed"):
            raise LessonImmutableException(
                "Проведённое или пропущенное занятие нельзя удалить - "
                "это часть истории посещений"
            )

        if lesson.lesson_date < today_in_studio_tz():
            raise LessonImmutableException(
                "Прошедшее занятие нельзя удалить. Если оно не состоялось, "
                "отметьте его отменённым"
            )

        result = await self.lesson_repo.delete_by_id(lesson_id)
        if result:
            logger.info("Deleted lesson %s", lesson_id)
        return result

    # ==================== ВНУТРЕННЕЕ ====================

    def _assert_transition_allowed(self, current: str, new: str) -> None:
        """Проверить допустимость перехода статуса."""
        if new not in ALLOWED_STATUS_TRANSITIONS.get(current, []):
            raise InvalidLessonStatusException(current, new)

    async def _assert_no_conflicts(
        self,
        candidate: LessonCandidate,
        exclude_lesson_id: Optional[int] = None,
    ) -> None:
        """
        Бросить исключение, если время занято.

        Проверяются все три ресурса сразу. Сообщение берётся по первому
        найденному конфликту - показывать пользователю список из десяти
        причин смысла нет, ему нужно понять, что слот занят.
        """
        report = await self.conflict_service.check_single(
            candidate, exclude_lesson_id=exclude_lesson_id
        )

        if not report.has_conflicts:
            return

        first = report.conflicts[0]
        message = CONFLICT_EXCEPTIONS.get(first.kind, "Время уже занято")

        from app.core.exceptions import (
            ClassroomConflictException,
            StudentConflictException,
            TeacherConflictException,
        )

        exception_by_kind = {
            ConflictKind.CLASSROOM: ClassroomConflictException,
            ConflictKind.TEACHER: TeacherConflictException,
            ConflictKind.STUDENT: StudentConflictException,
        }

        exception_class = exception_by_kind[first.kind]
        raise exception_class(
            lesson_date=str(candidate.lesson_date),
            time=candidate.start_time.strftime("%H:%M"),
        )