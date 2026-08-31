"""
Выборка занятий, способных конфликтовать с набором кандидатов.

Один ограниченный запрос вместо запроса на каждую проверяемую дату.

Старая проверка ходила в БД отдельно для каждой даты и только по кабинету
(get_by_classroom -> цикл в Python). При генерации на две недели это
превращалось в десятки запросов, а преподаватель и ученик не проверялись
вовсе.

Выборка сужается сразу по четырём осям: диапазон дат, преподаватели,
кабинеты, ученики. На горизонте генерации это десятки строк - объём,
который дешевле один раз вытащить и пересечь в памяти, чем описывать
пересечение интервалов средствами SQL.
"""

import logging
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.conflicts import ExistingLesson
from app.models.lesson import Lesson
from app.models.lesson_student import LessonStudent

logger = logging.getLogger(__name__)


# Отменённое занятие освобождает и кабинет, и преподавателя, и ученика.
# Условие намеренно совпадает с WHERE в EXCLUDE-констрейнтах на lessons:
# если оно разойдётся, сервис начнёт обещать пользователю то, что база
# потом отвергнет.
ACTIVE_STATUSES_FILTER = Lesson.status != "cancelled"


class ConflictRepository:
    """Читает занятия, которые могут пересечься с проверяемыми кандидатами."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_potentially_conflicting(
        self,
        *,
        from_date: date,
        to_date: date,
        teacher_ids: Optional[Iterable[int]] = None,
        classroom_ids: Optional[Iterable[int]] = None,
        student_ids: Optional[Iterable[int]] = None,
        exclude_lesson_ids: Optional[Iterable[int]] = None,
    ) -> List[ExistingLesson]:
        """
        Занятия в диапазоне дат, делящие хотя бы один ресурс с кандидатами.

        Args:
            from_date, to_date: границы включительно.
            teacher_ids: преподаватели кандидатов.
            classroom_ids: кабинеты кандидатов, без None.
            student_ids: ученики кандидатов.
            exclude_lesson_ids: занятия, которые не считаются конфликтом -
                обычно это само редактируемое занятие.

        Returns:
            Список ExistingLesson с уже подтянутыми student_ids.
        """
        teachers = {tid for tid in (teacher_ids or []) if tid is not None}
        classrooms = {cid for cid in (classroom_ids or []) if cid is not None}
        students = {sid for sid in (student_ids or []) if sid is not None}
        excluded = {lid for lid in (exclude_lesson_ids or []) if lid is not None}

        resource_filters = []

        if teachers:
            resource_filters.append(Lesson.teacher_id.in_(teachers))

        if classrooms:
            resource_filters.append(Lesson.classroom_id.in_(classrooms))

        if students:
            resource_filters.append(
                Lesson.id.in_(
                    select(LessonStudent.lesson_id).where(
                        LessonStudent.student_id.in_(students)
                    )
                )
            )

        # Ни одного ресурса для проверки - конфликтовать не с чем.
        # Важно не выродить запрос в or_() без аргументов: он вернул бы
        # все занятия периода.
        if not resource_filters:
            return []

        query = select(Lesson).where(
            and_(
                Lesson.lesson_date >= from_date,
                Lesson.lesson_date <= to_date,
                ACTIVE_STATUSES_FILTER,
                or_(*resource_filters),
            )
        )

        if excluded:
            query = query.where(Lesson.id.notin_(excluded))

        result = await self.db.execute(query)
        lessons = list(result.scalars().all())

        if not lessons:
            return []

        students_by_lesson = await self._fetch_students_by_lesson(
            [lesson.id for lesson in lessons]
        )

        return [
            ExistingLesson(
                lesson_id=lesson.id,
                lesson_date=lesson.lesson_date,
                start_time=lesson.start_time,
                end_time=lesson.end_time,
                teacher_id=lesson.teacher_id,
                classroom_id=lesson.classroom_id,
                student_ids=students_by_lesson.get(lesson.id, ()),
            )
            for lesson in lessons
        ]

    async def _fetch_students_by_lesson(
        self,
        lesson_ids: Sequence[int],
    ) -> Dict[int, Tuple[int, ...]]:
        """
        Ученики найденных занятий одним запросом.

        Отдельным запросом, а не join'ом к основной выборке: join размножил
        бы строки занятий по числу учеников, и их пришлось бы схлопывать
        обратно. Два простых запроса читаются лучше одного хитрого.
        """
        if not lesson_ids:
            return {}

        result = await self.db.execute(
            select(LessonStudent.lesson_id, LessonStudent.student_id).where(
                LessonStudent.lesson_id.in_(lesson_ids)
            )
        )

        grouped: Dict[int, List[int]] = {}
        for lesson_id, student_id in result.all():
            grouped.setdefault(lesson_id, []).append(student_id)

        return {
            lesson_id: tuple(sorted(students))
            for lesson_id, students in grouped.items()
        }