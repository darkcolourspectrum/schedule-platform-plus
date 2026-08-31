"""
Поиск конфликтов расписания.

Конфликт - это пересечение по времени между двумя занятиями, которые
делят один ресурс. Ресурсов три:

    кабинет         одно помещение не вмещает два занятия
    преподаватель   человек не может вести два занятия сразу
    ученик          ученик не может быть на двух занятиях сразу

Проверялся раньше только кабинет, и только он. Преподавателя можно было
поставить в два места одновременно, ученика - записать на два занятия.

Разделение ответственности:
    Этот модуль ничего не защищает. Защита стоит в базе - два
    EXCLUDE-констрейнта на lessons физически не дают вставить
    пересекающиеся занятия, включая случай двух одновременных запросов.

    Задача модуля - заранее СКАЗАТЬ, что конфликт будет: показать его
    в предпросмотре шаблона, дать генератору исключить проблемные даты
    до вставки, вернуть пользователю понятный 409 вместо 500.

    Поэтому расхождение между этим кодом и констрейнтом не может привести
    к порче данных. Худший исход - IntegrityError, который транслируется
    в ту же самую доменную ошибку (см. app/core/db_errors.py).

Все функции здесь чистые: на вход структуры, на выход структуры.
БД не трогается, запросы делает ConflictRepository.
"""

from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.domain.recurrence import times_overlap


class ConflictKind(str, Enum):
    """Какой ресурс не поделили."""

    CLASSROOM = "classroom"
    TEACHER = "teacher"
    STUDENT = "student"


@dataclass(frozen=True)
class LessonCandidate:
    """
    Занятие, которое мы собираемся создать или изменить.

    Используется и генератором (десятки кандидатов из шаблона),
    и созданием разового занятия (один кандидат), и переносом.

    Поле ref не участвует в логике - это метка вызывающей стороны,
    чтобы сопоставить кандидата с его источником. Генератор кладёт
    туда id слота, предпросмотр - индекс строки формы.
    """

    lesson_date: date
    start_time: time
    end_time: time
    teacher_id: int
    classroom_id: Optional[int] = None
    student_ids: Tuple[int, ...] = ()
    ref: Optional[str] = None


@dataclass(frozen=True)
class ExistingLesson:
    """Занятие, уже лежащее в БД. Собирается ConflictRepository."""

    lesson_id: int
    lesson_date: date
    start_time: time
    end_time: time
    teacher_id: int
    classroom_id: Optional[int] = None
    student_ids: Tuple[int, ...] = ()


@dataclass(frozen=True)
class Conflict:
    """
    Один найденный конфликт.

    candidate_index - позиция кандидата во входном списке.
    existing_lesson_id - с чем конфликтуем, если конфликт с уже
        существующим занятием.
    other_candidate_index - с чем конфликтуем, если оба занятия ещё
        не созданы (два слота одного шаблона легли на одну дату).
    Ровно одно из этих двух полей заполнено.

    subject_id - id ресурса: кабинета, преподавателя или ученика.
    """

    kind: ConflictKind
    candidate_index: int
    subject_id: int
    conflict_date: date
    candidate_start: time
    candidate_end: time
    other_start: time
    other_end: time
    existing_lesson_id: Optional[int] = None
    other_candidate_index: Optional[int] = None


@dataclass
class ConflictReport:
    """
    Итог проверки набора кандидатов.

    Готов к использованию сразу тремя потребителями:
        - генератор берёт conflict_free_indices и вставляет только их;
        - предпросмотр показывает conflicts пользователю;
        - создание одного занятия смотрит на has_conflicts.
    """

    conflicts: List[Conflict] = field(default_factory=list)
    total_candidates: int = 0

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def conflicting_indices(self) -> Set[int]:
        """Индексы кандидатов, у которых есть хотя бы один конфликт."""
        return {c.candidate_index for c in self.conflicts}

    @property
    def conflict_free_indices(self) -> List[int]:
        """Индексы кандидатов без конфликтов, в исходном порядке."""
        blocked = self.conflicting_indices
        return [i for i in range(self.total_candidates) if i not in blocked]

    def by_candidate(self) -> Dict[int, List[Conflict]]:
        """Конфликты, сгруппированные по индексу кандидата."""
        grouped: Dict[int, List[Conflict]] = {}
        for conflict in self.conflicts:
            grouped.setdefault(conflict.candidate_index, []).append(conflict)
        return grouped


# ==================== ПОИСК ====================


def _shared_students(a: Sequence[int], b: Sequence[int]) -> List[int]:
    """Ученики, встречающиеся в обоих занятиях."""
    return sorted(set(a) & set(b))


def find_conflicts_with_existing(
    candidates: Sequence[LessonCandidate],
    existing: Sequence[ExistingLesson],
) -> List[Conflict]:
    """
    Конфликты кандидатов с занятиями, которые уже есть в БД.

    Существующие занятия должны быть предварительно отфильтрованы:
    отменённые исключены, иначе освободившийся слот считался бы занятым.
    Этим занимается ConflictRepository, и его фильтр намеренно совпадает
    с условием WHERE в EXCLUDE-констрейнтах.
    """
    found: List[Conflict] = []

    for index, candidate in enumerate(candidates):
        for other in existing:
            if candidate.lesson_date != other.lesson_date:
                continue

            if not times_overlap(
                candidate.start_time,
                candidate.end_time,
                other.start_time,
                other.end_time,
            ):
                continue

            if (
                candidate.classroom_id is not None
                and candidate.classroom_id == other.classroom_id
            ):
                found.append(
                    Conflict(
                        kind=ConflictKind.CLASSROOM,
                        candidate_index=index,
                        subject_id=candidate.classroom_id,
                        conflict_date=candidate.lesson_date,
                        candidate_start=candidate.start_time,
                        candidate_end=candidate.end_time,
                        other_start=other.start_time,
                        other_end=other.end_time,
                        existing_lesson_id=other.lesson_id,
                    )
                )

            if candidate.teacher_id == other.teacher_id:
                found.append(
                    Conflict(
                        kind=ConflictKind.TEACHER,
                        candidate_index=index,
                        subject_id=candidate.teacher_id,
                        conflict_date=candidate.lesson_date,
                        candidate_start=candidate.start_time,
                        candidate_end=candidate.end_time,
                        other_start=other.start_time,
                        other_end=other.end_time,
                        existing_lesson_id=other.lesson_id,
                    )
                )

            for student_id in _shared_students(
                candidate.student_ids, other.student_ids
            ):
                found.append(
                    Conflict(
                        kind=ConflictKind.STUDENT,
                        candidate_index=index,
                        subject_id=student_id,
                        conflict_date=candidate.lesson_date,
                        candidate_start=candidate.start_time,
                        candidate_end=candidate.end_time,
                        other_start=other.start_time,
                        other_end=other.end_time,
                        existing_lesson_id=other.lesson_id,
                    )
                )

    return found


def find_conflicts_within_batch(
    candidates: Sequence[LessonCandidate],
) -> List[Conflict]:
    """
    Конфликты кандидатов между собой.

    Нужно, потому что генератор создаёт занятия пачкой. Два слота одного
    шаблона могут лечь на одну дату и одно время - в БД такого пересечения
    ещё нет, и проверка против существующих занятий его не увидит.

    Конфликт записывается один раз, на более позднего кандидата: так
    при отсеве по conflict_free_indices первое занятие уцелеет, а второе
    будет пропущено, вместо того чтобы потерять оба.
    """
    found: List[Conflict] = []

    for i in range(len(candidates)):
        first = candidates[i]
        for j in range(i + 1, len(candidates)):
            second = candidates[j]

            if first.lesson_date != second.lesson_date:
                continue

            if not times_overlap(
                first.start_time,
                first.end_time,
                second.start_time,
                second.end_time,
            ):
                continue

            if (
                first.classroom_id is not None
                and first.classroom_id == second.classroom_id
            ):
                found.append(
                    Conflict(
                        kind=ConflictKind.CLASSROOM,
                        candidate_index=j,
                        subject_id=first.classroom_id,
                        conflict_date=second.lesson_date,
                        candidate_start=second.start_time,
                        candidate_end=second.end_time,
                        other_start=first.start_time,
                        other_end=first.end_time,
                        other_candidate_index=i,
                    )
                )

            if first.teacher_id == second.teacher_id:
                found.append(
                    Conflict(
                        kind=ConflictKind.TEACHER,
                        candidate_index=j,
                        subject_id=first.teacher_id,
                        conflict_date=second.lesson_date,
                        candidate_start=second.start_time,
                        candidate_end=second.end_time,
                        other_start=first.start_time,
                        other_end=first.end_time,
                        other_candidate_index=i,
                    )
                )

            for student_id in _shared_students(
                first.student_ids, second.student_ids
            ):
                found.append(
                    Conflict(
                        kind=ConflictKind.STUDENT,
                        candidate_index=j,
                        subject_id=student_id,
                        conflict_date=second.lesson_date,
                        candidate_start=second.start_time,
                        candidate_end=second.end_time,
                        other_start=first.start_time,
                        other_end=first.end_time,
                        other_candidate_index=i,
                    )
                )

    return found


def build_report(
    candidates: Sequence[LessonCandidate],
    existing: Sequence[ExistingLesson],
) -> ConflictReport:
    """Полная проверка: и против БД, и внутри пачки."""
    conflicts = find_conflicts_with_existing(candidates, existing)
    conflicts.extend(find_conflicts_within_batch(candidates))

    return ConflictReport(
        conflicts=conflicts,
        total_candidates=len(candidates),
    )


__all__ = [
    "ConflictKind",
    "LessonCandidate",
    "ExistingLesson",
    "Conflict",
    "ConflictReport",
    "find_conflicts_with_existing",
    "find_conflicts_within_batch",
    "build_report",
]