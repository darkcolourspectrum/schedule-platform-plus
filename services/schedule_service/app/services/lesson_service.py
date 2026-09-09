"""
Сервис занятий: создание, изменение, статусы, посещаемость.

Три правила, на которых держится вся логика файла.

Статусы меняются только по таблице ALLOWED_STATUS_TRANSITIONS. Переходы
назад разрешены намеренно: отметка - решение человека, а человек
ошибается кнопкой. Единственный переход, требующий проверки конфликтов,
это cancelled -> scheduled: отменённое занятие освобождает слот, и за
время отмены его могли занять.

Посещаемость выводится из статуса занятия по ATTENDANCE_BY_STATUS.
Поимённая отметка - механизм исключения для групповых занятий, где
пришли не все, а не обязательный шаг.

Время делит операции надвое. До окончания занятия его можно перенести
или отменить, но нельзя отметить результат - результата ещё нет. После
окончания наоборот. Границей служит время окончания в часовом поясе
студии, а не дата: у идущего занятия отмечать тоже нечего.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidLessonStatusException,
    LessonImmutableException,
    LessonNotFoundException,
    LessonNotEndedException,
    InvalidAttendanceException,
)
from app.domain.conflicts import ConflictKind, LessonCandidate
from app.domain.statuses import AttendanceStatus, LessonStatus
from app.domain.recurrence import (
    calculate_end_time,
    duration_minutes_between,
    today_in_studio_tz,
    lesson_has_ended,
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
# Из этих переходов проверки конфликтов требует только cancelled ->
# scheduled: отменённое занятие исключено из EXCLUDE-констрейнтов,
# то есть его слот считается свободным. Проведённое, пропущенное и
# сорванное слот не освобождают, поэтому их возврат в scheduled ничего
# не бронирует заново.
#
# Три несостоявшихся статуса переходят друг в друга свободно: выяснить,
# что виноват был не ученик, а преподаватель, можно и через неделю.
ALLOWED_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    LessonStatus.SCHEDULED: [
        LessonStatus.COMPLETED,
        LessonStatus.CANCELLED,
        LessonStatus.MISSED,
        LessonStatus.TEACHER_MISSED,
    ],
    LessonStatus.COMPLETED: [
        LessonStatus.SCHEDULED,
        LessonStatus.MISSED,
        LessonStatus.TEACHER_MISSED,
    ],
    LessonStatus.MISSED: [
        LessonStatus.SCHEDULED,
        LessonStatus.COMPLETED,
        LessonStatus.TEACHER_MISSED,
    ],
    LessonStatus.TEACHER_MISSED: [
        LessonStatus.SCHEDULED,
        LessonStatus.COMPLETED,
        LessonStatus.MISSED,
    ],
    LessonStatus.CANCELLED: [LessonStatus.SCHEDULED],
}

# Статус занятия -> статус посещения учеников по умолчанию.
#
# Единственный источник правды для этого соответствия. Отсюда следует
# главное свойство модели: посещаемость выводится из статуса занятия
# автоматически, и в норме преподаватель не отмечает никого поимённо.
#
# teacher_missed даёт ученикам 'cancelled', а не пропуск: они пришли
# и не виноваты, что занятия не было.
ATTENDANCE_BY_STATUS = {
    LessonStatus.SCHEDULED: AttendanceStatus.SCHEDULED,
    LessonStatus.COMPLETED: AttendanceStatus.ATTENDED,
    LessonStatus.CANCELLED: AttendanceStatus.CANCELLED,
    LessonStatus.MISSED: AttendanceStatus.MISSED,
    LessonStatus.TEACHER_MISSED: AttendanceStatus.CANCELLED,
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

        if lesson.status in LessonStatus.FINAL:
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
            self._assert_not_ended(lesson, "перенести")
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

        self._assert_not_ended(lesson, "отменить")

        self._assert_transition_allowed(lesson.status, LessonStatus.CANCELLED)

        lesson.status = LessonStatus.CANCELLED
        if reason:
            lesson.cancellation_reason = reason

        lesson = await self.lesson_repo.update_obj(lesson)
        await self.lesson_repo.set_attendance_for_all(lesson_id, ATTENDANCE_BY_STATUS[LessonStatus.CANCELLED])

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

        if lesson.status == LessonStatus.SCHEDULED:
            return lesson

        self._assert_transition_allowed(lesson.status, LessonStatus.SCHEDULED)

        if lesson.status == LessonStatus.CANCELLED:
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

        lesson.status = LessonStatus.SCHEDULED
        lesson.cancellation_reason = None

        lesson = await self.lesson_repo.update_obj(lesson)
        await self.lesson_repo.set_attendance_for_all(lesson_id, ATTENDANCE_BY_STATUS[LessonStatus.SCHEDULED])

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
                Не указана - все считаются присутствовавшими. Указанная
                трактуется как список исключений, а не как полный
                список: неупомянутые всё равно получат 'attended'.

        Раздельная посещаемость нужна, потому что "занятие не состоялось"
        и "один ученик не пришёл" - разные события. Для группового занятия
        второе не должно отменять первое.
        """
        
        lesson = await self.get_lesson(lesson_id)
        self._assert_ended(lesson)

        student_ids = await self.lesson_repo.get_student_ids(lesson_id)
        self._validate_attendance(attendance, student_ids)

        # Занятие уже проведено - значит это правка посещаемости, а не
        # смена статуса. Прогонять её через таблицу переходов нельзя:
        # completed -> completed там нет и быть не должно, но исправить
        # ошибочную отметку человек обязан иметь возможность.
        if lesson.status != LessonStatus.COMPLETED:
            self._assert_transition_allowed(lesson.status, LessonStatus.COMPLETED)
            lesson.status = LessonStatus.COMPLETED
            lesson = await self.lesson_repo.update_obj(lesson)

        # Сначала значение по умолчанию всем, потом поимённые исключения.
        # Порядок важен: без первого шага ученик, которого преподаватель
        # не упомянул, остался бы в 'scheduled' на проведённом занятии -
        # неотличимо от занятия, до которого вообще не дошли руки.
        await self.lesson_repo.set_attendance_for_all(
            lesson_id, ATTENDANCE_BY_STATUS[LessonStatus.COMPLETED]
        )
        if attendance:
            await self.lesson_repo.set_attendance_bulk(lesson_id, attendance)

        logger.info("Completed lesson %s", lesson_id)
        return lesson

    async def mark_as_missed(self, lesson_id: int) -> Lesson:
        """Отметить занятие как несостоявшееся по вине ученика."""
        lesson = await self.get_lesson(lesson_id)
        self._assert_ended(lesson)
        self._assert_transition_allowed(lesson.status, LessonStatus.MISSED)

        lesson.status = LessonStatus.MISSED
        lesson = await self.lesson_repo.update_obj(lesson)
        
        await self.lesson_repo.set_attendance_for_all(
            lesson_id, ATTENDANCE_BY_STATUS[LessonStatus.MISSED]
        )

        logger.info("Marked lesson %s as missed", lesson_id)
        return lesson

    async def mark_as_teacher_missed(self, lesson_id: int) -> Lesson:
        """
        Отметить, что занятие не состоялось по вине преподавателя.

        Отдельный статус, а не причина строкой: последствия принципиально
        разные. После прогула преподавателя отработка положена
        безусловно, после прогула ученика - на усмотрение студии.
        Различить это разбором текстовой причины потом невозможно.

        От отмены отличается моментом: отмена - решение, принятое
        заранее, освобождающее слот. Здесь занятие уже прошло.
        """
        lesson = await self.get_lesson(lesson_id)
        self._assert_ended(lesson)
        self._assert_transition_allowed(lesson.status, LessonStatus.TEACHER_MISSED)

        lesson.status = LessonStatus.TEACHER_MISSED
        lesson = await self.lesson_repo.update_obj(lesson)
        await self.lesson_repo.set_attendance_for_all(
            lesson_id, ATTENDANCE_BY_STATUS[LessonStatus.TEACHER_MISSED]
        )

        logger.info("Marked lesson %s as teacher_missed", lesson_id)
        return lesson

    # ==================== УДАЛЕНИЕ ====================

    async def delete_lesson(self, lesson_id: int) -> bool:
        """
        Удалить занятие.

        Удалить можно только запланированное занятие в будущем. Всё
        остальное - история: она нужна аналитике, отчётам и разбору
        спорных ситуаций. Для прошедшего занятия правильное действие -
        отметить, состоялось оно или нет.
        """
        lesson = await self.get_lesson(lesson_id)

        if lesson.status in LessonStatus.FINAL:
            raise LessonImmutableException(
                "Проведённое или пропущенное занятие нельзя удалить - "
                "это часть истории посещений"
            )

        if lesson.lesson_date < today_in_studio_tz():
            raise LessonImmutableException(
                "Прошедшее занятие нельзя удалить. Если оно не состоялось, "
                "отметьте, что оно не состоялось"
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

    def _assert_ended(self, lesson: Lesson) -> None:
        """
        Результат ставится только у закончившегося занятия.

        До окончания результата не существует: занятие либо ещё впереди,
        либо идёт прямо сейчас и неизвестно, чем кончится.
        """
        if not lesson_has_ended(lesson.lesson_date, lesson.end_time):
            raise LessonNotEndedException(
                "Занятие ещё не закончилось. Отметить результат можно "
                "после времени его окончания"
            )

    def _assert_not_ended(self, lesson: Lesson, action: str) -> None:
        """
        Планировать можно только то, что ещё не произошло.

        Без этой проверки вчерашнее занятие можно было перенести на
        завтра, и следа о том, что оно уже было, не оставалось.
        """
        if lesson_has_ended(lesson.lesson_date, lesson.end_time):
            raise LessonImmutableException(
                f"Занятие уже прошло, {action} его нельзя. "
                f"Отметьте, состоялось оно или нет"
            )

    def _validate_attendance(
        self,
        attendance: Optional[Dict[int, str]],
        student_ids: List[int],
    ) -> None:
        """
        Проверить поимённую посещаемость до записи.

        Две вещи, которые иначе прошли бы молча. Чужой ученик в словаре
        не обновил бы ни одной строки, и преподаватель считал бы, что
        отметил его. А занятие, на которое не пришёл никто, - это не
        проведённое занятие, а несостоявшееся, и статус у него другой.
        """
        if not attendance:
            return

        unknown = set(attendance) - set(student_ids)
        if unknown:
            raise InvalidAttendanceException(
                f"Эти ученики не записаны на занятие: {sorted(unknown)}"
            )

        default = ATTENDANCE_BY_STATUS[LessonStatus.COMPLETED]
        someone_came = any(
            attendance.get(student_id, default) == AttendanceStatus.ATTENDED
            for student_id in student_ids
        )
        if student_ids and not someone_came:
            raise InvalidAttendanceException(
                "Не пришёл никто из учеников - такое занятие не является "
                "проведённым. Отметьте, что оно не состоялось"
            )

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