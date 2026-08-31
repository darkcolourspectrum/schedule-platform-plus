"""
Проверка доменного ядра расчёта повторений.

Запуск:
    docker compose exec schedule-service python scripts/check_recurrence.py

Скрипт не трогает БД и ничего не меняет. Он прогоняет набор сценариев
через app/domain/recurrence.py и печатает результат. Всё, что помечено
FAIL, означает расхождение между ожиданием и поведением кода.

Это не замена автотестам, а быстрый способ убедиться своими глазами,
что даты считаются так, как задумано, до того как на этой логике будет
построен генератор.
"""

import sys
from datetime import date, time

from app.domain.recurrence import (
    LessonCrossesMidnightError,
    InvalidDayOfWeekError,
    InvalidWeekIntervalError,
    calculate_end_time,
    duration_minutes_between,
    find_overlapping_slot_pairs,
    first_occurrence_on_or_after,
    generation_horizon_end,
    monday_of_week,
    slot_occurrence_dates,
    times_overlap,
    today_in_studio_tz,
)


passed = 0
failed = 0


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


def check_raises(label: str, exc_type, fn) -> None:
    global passed, failed
    try:
        fn()
    except exc_type:
        passed += 1
        print(f"  OK   {label}")
        return
    except Exception as exc:
        failed += 1
        print(f"  FAIL {label}")
        print(f"       ожидалось исключение {exc_type.__name__}")
        print(f"       получено {type(exc).__name__}: {exc}")
        return
    failed += 1
    print(f"  FAIL {label}")
    print(f"       ожидалось исключение {exc_type.__name__}, ничего не упало")


print()
print("== Часовой пояс ==")
print(f"  Сегодня в часовом поясе студии: {today_in_studio_tz()}")
print(f"  Горизонт генерации до:          {generation_horizon_end()}")
print("  Сверь первую дату с реальной датой в Томске, а не на сервере.")

print()
print("== Арифметика времени ==")
check("10:00 + 60 мин = 11:00", calculate_end_time(time(10, 0), 60), time(11, 0))
check("18:30 + 45 мин = 19:15", calculate_end_time(time(18, 30), 45), time(19, 15))
check("22:00 + 90 мин = 23:30", calculate_end_time(time(22, 0), 90), time(23, 30))
check_raises(
    "23:30 + 60 мин отклоняется (переход через полночь)",
    LessonCrossesMidnightError,
    lambda: calculate_end_time(time(23, 30), 60),
)
check_raises(
    "23:00 + 60 мин отклоняется (конец ровно в полночь)",
    LessonCrossesMidnightError,
    lambda: calculate_end_time(time(23, 0), 60),
)
check("длительность 10:00-11:30 = 90", duration_minutes_between(time(10, 0), time(11, 30)), 90)

print()
print("== Пересечение интервалов ==")
check(
    "10:00-11:00 и 10:30-11:30 пересекаются",
    times_overlap(time(10, 0), time(11, 0), time(10, 30), time(11, 30)),
    True,
)
check(
    "10:00-11:00 и 11:00-12:00 идут подряд, не конфликт",
    times_overlap(time(10, 0), time(11, 0), time(11, 0), time(12, 0)),
    False,
)

print()
print("== Поиск дня недели ==")
# 2026-09-01 - вторник (isoweekday 2).
check("от вторника ищем вторник = тот же день", first_occurrence_on_or_after(date(2026, 9, 1), 2), date(2026, 9, 1))
check("от вторника ищем четверг = +2 дня", first_occurrence_on_or_after(date(2026, 9, 1), 4), date(2026, 9, 3))
check("от вторника ищем понедельник = +6 дней", first_occurrence_on_or_after(date(2026, 9, 1), 1), date(2026, 9, 7))
check("понедельник недели 2026-09-01", monday_of_week(date(2026, 9, 1)), date(2026, 8, 31))
check_raises(
    "день недели 0 отклоняется",
    InvalidDayOfWeekError,
    lambda: first_occurrence_on_or_after(date(2026, 9, 1), 0),
)
check_raises(
    "день недели 8 отклоняется",
    InvalidDayOfWeekError,
    lambda: first_occurrence_on_or_after(date(2026, 9, 1), 8),
)

print()
print("== Даты повторения: каждую неделю ==")
check(
    "вторники с 01.09 по 30.09",
    slot_occurrence_dates(
        day_of_week=2,
        valid_from=date(2026, 9, 1),
        valid_until=None,
        anchor_date=date(2026, 9, 1),
        week_interval=1,
        horizon_end=date(2026, 9, 30),
    ),
    [date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15), date(2026, 9, 22), date(2026, 9, 29)],
)
check(
    "valid_until обрезает раньше горизонта",
    slot_occurrence_dates(
        day_of_week=2,
        valid_from=date(2026, 9, 1),
        valid_until=date(2026, 9, 16),
        anchor_date=date(2026, 9, 1),
        week_interval=1,
        horizon_end=date(2026, 9, 30),
    ),
    [date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15)],
)
check(
    "шаблон начинается после горизонта - пусто",
    slot_occurrence_dates(
        day_of_week=2,
        valid_from=date(2026, 10, 1),
        valid_until=None,
        anchor_date=date(2026, 10, 1),
        week_interval=1,
        horizon_end=date(2026, 9, 30),
    ),
    [],
)

print()
print("== Даты повторения: раз в две недели ==")
check(
    "чётные недели от опорной даты 01.09",
    slot_occurrence_dates(
        day_of_week=2,
        valid_from=date(2026, 9, 1),
        valid_until=None,
        anchor_date=date(2026, 9, 1),
        week_interval=2,
        horizon_end=date(2026, 10, 31),
    ),
    [date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 29), date(2026, 10, 13), date(2026, 10, 27)],
)
check(
    "опорная дата сдвинута на неделю - сетка сдвигается",
    slot_occurrence_dates(
        day_of_week=2,
        valid_from=date(2026, 9, 1),
        valid_until=None,
        anchor_date=date(2026, 8, 25),
        week_interval=2,
        horizon_end=date(2026, 10, 31),
    ),
    [date(2026, 9, 8), date(2026, 9, 22), date(2026, 10, 6), date(2026, 10, 20)],
)
check_raises(
    "периодичность 3 отклоняется",
    InvalidWeekIntervalError,
    lambda: slot_occurrence_dates(
        day_of_week=2,
        valid_from=date(2026, 9, 1),
        valid_until=None,
        anchor_date=date(2026, 9, 1),
        week_interval=3,
        horizon_end=date(2026, 9, 30),
    ),
)

print()
print("== Пересечение слотов внутри шаблона ==")
check(
    "вторник 18:00 и четверг 19:30 - разные дни, ок",
    find_overlapping_slot_pairs([(2, time(18, 0), 60), (4, time(19, 30), 45)]),
    [],
)
check(
    "вторник 18:00 60мин и вторник 19:00 60мин - подряд, ок",
    find_overlapping_slot_pairs([(2, time(18, 0), 60), (2, time(19, 0), 60)]),
    [],
)
check(
    "вторник 18:00 60мин и вторник 18:30 45мин - пересечение",
    find_overlapping_slot_pairs([(2, time(18, 0), 60), (2, time(18, 30), 45)]),
    [(0, 1)],
)

print()
print(f"== Итого: {passed} пройдено, {failed} провалено ==")
print()

sys.exit(1 if failed else 0)