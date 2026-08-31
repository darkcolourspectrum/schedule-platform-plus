"""
Проверка доменной логики конфликтов.

Запуск:
    docker compose exec schedule-service python scripts/check_conflicts.py

Скрипт не трогает БД. Он собирает кандидатов и существующие занятия
руками и проверяет, что конфликты находятся по всем трём осям:
кабинет, преподаватель, ученик.
"""

import sys
from datetime import date, time

from app.domain.conflicts import (
    ConflictKind,
    ExistingLesson,
    LessonCandidate,
    build_report,
    find_conflicts_within_batch,
    find_conflicts_with_existing,
)


passed = 0
failed = 0

D = date(2026, 9, 1)


def check(label: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")
        print(f"       ожидалось: {expected}")
        print(f"       получено:  {actual}")


def kinds(conflicts):
    return sorted({c.kind.value for c in conflicts})


def candidate(**kwargs):
    base = dict(
        lesson_date=D,
        start_time=time(10, 0),
        end_time=time(11, 0),
        teacher_id=1,
        classroom_id=1,
        student_ids=(100,),
    )
    base.update(kwargs)
    return LessonCandidate(**base)


def existing(**kwargs):
    base = dict(
        lesson_id=999,
        lesson_date=D,
        start_time=time(10, 0),
        end_time=time(11, 0),
        teacher_id=1,
        classroom_id=1,
        student_ids=(100,),
    )
    base.update(kwargs)
    return ExistingLesson(**base)


print()
print("== Конфликт по кабинету ==")
check(
    "тот же кабинет, пересечение по времени, другой препод и ученик",
    kinds(
        find_conflicts_with_existing(
            [candidate(teacher_id=1, student_ids=(100,))],
            [existing(teacher_id=2, student_ids=(200,), start_time=time(10, 30), end_time=time(11, 30))],
        )
    ),
    ["classroom"],
)
check(
    "тот же кабинет, занятия идут подряд - не конфликт",
    find_conflicts_with_existing(
        [candidate(start_time=time(11, 0), end_time=time(12, 0), teacher_id=2, student_ids=(200,))],
        [existing(teacher_id=1, student_ids=(100,))],
    ),
    [],
)
check(
    "разные кабинеты, разные люди - не конфликт",
    find_conflicts_with_existing(
        [candidate(classroom_id=1, teacher_id=1, student_ids=(100,))],
        [existing(classroom_id=2, teacher_id=2, student_ids=(200,))],
    ),
    [],
)
check(
    "оба онлайн (classroom_id=None) - кабинет не конфликтует",
    kinds(
        find_conflicts_with_existing(
            [candidate(classroom_id=None, teacher_id=1, student_ids=(100,))],
            [existing(classroom_id=None, teacher_id=2, student_ids=(200,))],
        )
    ),
    [],
)

print()
print("== Конфликт по преподавателю ==")
check(
    "один препод в двух разных кабинетах одновременно",
    kinds(
        find_conflicts_with_existing(
            [candidate(classroom_id=1, teacher_id=7, student_ids=(100,))],
            [existing(classroom_id=2, teacher_id=7, student_ids=(200,))],
        )
    ),
    ["teacher"],
)
check(
    "один препод, онлайн и очно одновременно - всё равно конфликт",
    kinds(
        find_conflicts_with_existing(
            [candidate(classroom_id=None, teacher_id=7, student_ids=(100,))],
            [existing(classroom_id=2, teacher_id=7, student_ids=(200,))],
        )
    ),
    ["teacher"],
)

print()
print("== Конфликт по ученику ==")
check(
    "один ученик на двух занятиях у разных преподавателей",
    kinds(
        find_conflicts_with_existing(
            [candidate(classroom_id=1, teacher_id=1, student_ids=(100, 101))],
            [existing(classroom_id=2, teacher_id=2, student_ids=(101, 102))],
        )
    ),
    ["student"],
)
check(
    "групповое занятие, пересекающихся учеников нет",
    find_conflicts_with_existing(
        [candidate(classroom_id=1, teacher_id=1, student_ids=(100, 101))],
        [existing(classroom_id=2, teacher_id=2, student_ids=(200, 201))],
    ),
    [],
)

print()
print("== Три конфликта сразу ==")
check(
    "тот же кабинет, тот же препод, тот же ученик",
    kinds(find_conflicts_with_existing([candidate()], [existing()])),
    ["classroom", "student", "teacher"],
)

print()
print("== Отмена даты не влияет ==")
check(
    "другая дата - конфликта нет",
    find_conflicts_with_existing(
        [candidate(lesson_date=date(2026, 9, 2))],
        [existing(lesson_date=date(2026, 9, 1))],
    ),
    [],
)

print()
print("== Конфликты внутри пачки кандидатов ==")
batch = [
    candidate(start_time=time(10, 0), end_time=time(11, 0)),
    candidate(start_time=time(10, 30), end_time=time(11, 30)),
]
batch_conflicts = find_conflicts_within_batch(batch)
check("два пересекающихся кандидата дают конфликты", bool(batch_conflicts), True)
check(
    "конфликт записан на второго кандидата, первый уцелеет",
    sorted({c.candidate_index for c in batch_conflicts}),
    [1],
)

print()
print("== Отчёт ==")
report = build_report(
    [
        candidate(lesson_date=date(2026, 9, 1)),
        candidate(lesson_date=date(2026, 9, 8)),
        candidate(lesson_date=date(2026, 9, 15)),
    ],
    [existing(lesson_date=date(2026, 9, 8))],
)
check("всего кандидатов", report.total_candidates, 3)
check("есть конфликты", report.has_conflicts, True)
check("заблокирован только второй", sorted(report.conflicting_indices), [1])
check("к вставке годятся первый и третий", report.conflict_free_indices, [0, 2])

empty = build_report([candidate()], [])
check("без существующих занятий конфликтов нет", empty.has_conflicts, False)
check("кандидат проходит", empty.conflict_free_indices, [0])

print()
print(f"== Итого: {passed} пройдено, {failed} провалено ==")
print()

sys.exit(1 if failed else 0)