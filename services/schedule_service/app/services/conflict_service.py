"""
Единая точка проверки конфликтов расписания.

Все пути, создающие или двигающие занятия, проходят через этот сервис:
разовое занятие, перенос, генерация из шаблона, предпросмотр шаблона,
восстановление отменённого занятия.

Раньше каждый путь проверял конфликты по-своему, а некоторые не проверяли
вовсе. Восстановление отменённого занятия, например, не смотрело ни на
что: слот мог быть уже занят, и cancelled -> scheduled создавал двойное
бронирование.

Сервис ничего не пишет в БД и не решает, что делать с конфликтом.
Он отвечает на вопрос "что будет, если создать вот это" и возвращает
структуру. Решение принимает вызывающий: генератор пропустит
конфликтующие даты, создание занятия бросит 409, предпросмотр покажет
список пользователю.
"""

import logging
from typing import Iterable, List, Optional, Sequence

from app.domain.conflicts import (
    ConflictReport,
    ExistingLesson,
    LessonCandidate,
    build_report,
)
from app.repositories.conflict_repository import ConflictRepository

logger = logging.getLogger(__name__)


class ConflictService:
    """Проверка пересечений по кабинету, преподавателю и ученику."""

    def __init__(self, conflict_repo: ConflictRepository):
        self.conflict_repo = conflict_repo

    async def check_candidates(
        self,
        candidates: Sequence[LessonCandidate],
        exclude_lesson_ids: Optional[Iterable[int]] = None,
    ) -> ConflictReport:
        """
        Проверить набор кандидатов и вернуть полный отчёт.

        Args:
            candidates: занятия, которые предполагается создать.
            exclude_lesson_ids: занятия, не считающиеся конфликтом.
                При переносе сюда передаётся id самого занятия, иначе
                оно конфликтовало бы само с собой.

        Returns:
            ConflictReport. Пустой отчёт при пустом входе.
        """
        if not candidates:
            return ConflictReport(conflicts=[], total_candidates=0)

        existing = await self._fetch_relevant_lessons(
            candidates, exclude_lesson_ids
        )

        report = build_report(candidates, existing)

        if report.has_conflicts:
            logger.info(
                "Conflict check: %s of %s candidates blocked, %s conflicts total",
                len(report.conflicting_indices),
                report.total_candidates,
                len(report.conflicts),
            )

        return report

    async def check_single(
        self,
        candidate: LessonCandidate,
        exclude_lesson_id: Optional[int] = None,
    ) -> ConflictReport:
        """
        Проверить одно занятие.

        Обёртка над check_candidates для путей, где кандидат ровно один:
        создание разового занятия, перенос, восстановление отменённого.
        """
        exclude = [exclude_lesson_id] if exclude_lesson_id else None
        return await self.check_candidates([candidate], exclude)

    async def _fetch_relevant_lessons(
        self,
        candidates: Sequence[LessonCandidate],
        exclude_lesson_ids: Optional[Iterable[int]],
    ) -> List[ExistingLesson]:
        """
        Вытащить занятия, способные пересечься с кандидатами.

        Границы запроса выводятся из самих кандидатов: минимальная и
        максимальная дата, множества преподавателей, кабинетов и учеников.
        Ничего сверх этого из БД не читается.
        """
        dates = [candidate.lesson_date for candidate in candidates]

        teacher_ids = {candidate.teacher_id for candidate in candidates}

        classroom_ids = {
            candidate.classroom_id
            for candidate in candidates
            if candidate.classroom_id is not None
        }

        student_ids = {
            student_id
            for candidate in candidates
            for student_id in candidate.student_ids
        }

        return await self.conflict_repo.fetch_potentially_conflicting(
            from_date=min(dates),
            to_date=max(dates),
            teacher_ids=teacher_ids,
            classroom_ids=classroom_ids,
            student_ids=student_ids,
            exclude_lesson_ids=exclude_lesson_ids,
        )