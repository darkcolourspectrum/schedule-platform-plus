"""
Расчёт дат повторения и арифметика времени.

Единственное место в сервисе, где решается:
    - какое сегодня число (с учётом часового пояса студии, а не сервера);
    - во сколько заканчивается занятие;
    - на какие конкретно даты попадает слот шаблона;
    - какие дни недели вообще рабочие.

Все функции чистые: не ходят в БД, не пишут логи, не имеют состояния.
Их поведение полностью определяется аргументами, поэтому их можно
проверить запуском scripts/check_recurrence.py.

Соглашения:
    - День недели везде ISO: 1 = понедельник, 7 = воскресенье
      (совпадает с date.isoweekday() и с колонкой day_of_week).
    - Секунды во времени начала игнорируются: расписание студии
      оперирует минутами.
    - Занятие не может пересекать полночь. Это не ограничение предметной
      области, а следствие того, что дата и время хранятся раздельно:
      занятие с 23:30 до 00:30 логически принадлежит двум датам, и любая
      попытка уложить его в одну строку ломает и сортировку, и проверку
      пересечений. Такой ввод отклоняется явной ошибкой.
"""

from datetime import date, datetime, time, timedelta
from typing import List, Optional, Sequence, Tuple

import pytz

from app.config import settings


# Часовой пояс студии. Берётся из SCHEDULE_TIMEZONE, по умолчанию Asia/Tomsk.
# Используется pytz, потому что он уже в зависимостях сервиса.
SCHEDULE_TZ = pytz.timezone(settings.schedule_timezone)

MINUTES_PER_DAY = 24 * 60

# Рабочие дни студии, ISO 1-7. Задаются через SCHEDULE_WORKING_DAYS.
#
# Воскресенье по умолчанию исключено. Дело не только в том, что студия
# не работает: календарь на фронте рисует шесть колонок, Пн-Сб, и занятие
# на воскресенье оказалось бы невидимым - оно существовало бы в базе,
# занимало кабинет и конфликтовало с другими, не показываясь нигде.
WORKING_DAYS = frozenset(settings.working_days_set)

# Названия дней недели, ISO 1-7. Живут здесь, а не в схемах API, потому
# что нужны в трёх местах сразу: валидация формы, ответ эндпоинта и текст
# события для рассылки. Один словарь - гарантия, что ученик и админ видят
# один и тот же день одним и тем же словом.
DAY_NAMES = {
    1: "понедельник",
    2: "вторник",
    3: "среда",
    4: "четверг",
    5: "пятница",
    6: "суббота",
    7: "воскресенье",
}

class RecurrenceError(ValueError):
    """Базовая ошибка расчёта повторений. Ловится сервисным слоем."""


class LessonCrossesMidnightError(RecurrenceError):
    """Занятие выходит за пределы суток."""

    def __init__(self, start_time: time, duration_minutes: int):
        self.start_time = start_time
        self.duration_minutes = duration_minutes
        super().__init__(
            f"Занятие в {start_time.strftime('%H:%M')} длительностью "
            f"{duration_minutes} мин выходит за пределы суток. "
            f"Занятие должно начинаться и заканчиваться в один день"
        )


class InvalidDayOfWeekError(RecurrenceError):
    """День недели вне диапазона 1-7."""

    def __init__(self, day_of_week: int):
        self.day_of_week = day_of_week
        super().__init__(
            f"Некорректный день недели: {day_of_week}. Ожидается 1-7, "
            f"где 1 - понедельник, 7 - воскресенье"
        )


class NonWorkingDayError(RecurrenceError):
    """День недели не входит в рабочие дни студии."""

    def __init__(self, day_of_week: int):
        self.day_of_week = day_of_week
        super().__init__(
            f"День недели {day_of_week} не является рабочим днём студии. "
            f"Рабочие дни: {sorted(WORKING_DAYS)}"
        )


class InvalidWeekIntervalError(RecurrenceError):
    """Периодичность вне поддерживаемых значений."""

    def __init__(self, week_interval: int):
        self.week_interval = week_interval
        super().__init__(
            f"Некорректная периодичность: {week_interval}. "
            f"Поддерживается 1 (каждую неделю) или 2 (раз в две недели)"
        )


# ==================== РАБОЧИЕ ДНИ ====================


def is_working_day(day: date) -> bool:
    """Попадает ли дата на рабочий день студии."""
    return day.isoweekday() in WORKING_DAYS


def assert_working_day_of_week(day_of_week: int) -> None:
    """
    Проверить, что день недели рабочий.

    Raises:
        InvalidDayOfWeekError: значение вне 1-7.
        NonWorkingDayError: день корректен, но студия в этот день не работает.
    """
    if not 1 <= day_of_week <= 7:
        raise InvalidDayOfWeekError(day_of_week)
    if day_of_week not in WORKING_DAYS:
        raise NonWorkingDayError(day_of_week)


# ==================== ТЕКУЩАЯ ДАТА ====================


def today_in_studio_tz() -> date:
    """
    Сегодняшняя дата в часовом поясе студии.

    Единственный допустимый способ узнать "сегодня" в этом сервисе.
    Прямой date.today() возвращает дату процесса, а процесс в контейнере
    живёт по UTC: при Asia/Tomsk (UTC+7) с полуночи до семи утра по
    местному времени сервис считал бы, что сегодня всё ещё вчера.
    """
    return datetime.now(SCHEDULE_TZ).date()


def generation_horizon_end(from_day: Optional[date] = None) -> date:
    """
    Последняя дата, до которой генерируем занятия.

    Горизонт задаётся настройкой SCHEDULE_GENERATION_WEEKS (по умолчанию 2).
    Он же служит предохранителем: даже у бессрочного шаблона за один
    прогон не может появиться больше занятий, чем помещается в горизонт.
    """
    base = from_day or today_in_studio_tz()
    return base + timedelta(weeks=settings.schedule_generation_weeks)


# ==================== АРИФМЕТИКА ВРЕМЕНИ ====================


def calculate_end_time(start_time: time, duration_minutes: int) -> time:
    """
    Время окончания занятия.

    Raises:
        LessonCrossesMidnightError: если занятие не укладывается в сутки.

    Занятие, заканчивающееся ровно в 00:00, тоже отклоняется: тип time
    не умеет представлять 24:00, а полночь как end_time дала бы
    end_time < start_time и сломала бы констрейнт ck_lesson_time_order
    и все проверки пересечений.
    """
    if duration_minutes <= 0:
        raise RecurrenceError(
            f"Длительность занятия должна быть положительной, "
            f"получено: {duration_minutes}"
        )

    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = start_minutes + duration_minutes

    if end_minutes >= MINUTES_PER_DAY:
        raise LessonCrossesMidnightError(start_time, duration_minutes)

    return time(hour=end_minutes // 60, minute=end_minutes % 60)


def duration_minutes_between(start_time: time, end_time: time) -> int:
    """
    Длительность в минутах между двумя временами одних суток.

    Обратная операция к calculate_end_time. Используется там, где занятие
    уже лежит в БД с парой start/end, а форме нужна длительность.
    """
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    return end_minutes - start_minutes


def times_overlap(
    start_a: time,
    end_a: time,
    start_b: time,
    end_b: time,
) -> bool:
    """
    Пересекаются ли два интервала в пределах одних суток.

    Границы не считаются пересечением: занятие 10:00-11:00 и занятие
    11:00-12:00 идут подряд и конфликтом не являются.
    """
    return start_a < end_b and start_b < end_a


# ==================== ДАТЫ ПОВТОРЕНИЯ ====================


def monday_of_week(day: date) -> date:
    """Понедельник той недели, в которую попадает переданная дата."""
    return day - timedelta(days=day.isoweekday() - 1)


def first_occurrence_on_or_after(day: date, day_of_week: int) -> date:
    """
    Первая дата не раньше day, попадающая на нужный день недели.

    Считается арифметикой, а не циклом. Прежняя реализация крутила
    while next_date.isoweekday() != day_of_week и зациклилась бы навсегда,
    если бы в day_of_week попал 0 или 8.
    """
    if not 1 <= day_of_week <= 7:
        raise InvalidDayOfWeekError(day_of_week)

    shift = (day_of_week - day.isoweekday()) % 7
    return day + timedelta(days=shift)


def slot_occurrence_dates(
    *,
    day_of_week: int,
    valid_from: date,
    valid_until: Optional[date],
    anchor_date: date,
    week_interval: int,
    horizon_end: date,
) -> List[date]:
    """
    Все даты, на которые попадает слот в пределах горизонта.

    Это полное целевое множество: генератор сравнивает его с тем, что уже
    есть в БД, и создаёт только недостающее. Никаких курсоров по последнему
    занятию - именно они порождали дубли, когда история занятий рвалась.

    Args:
        day_of_week: день недели слота, 1-7 (ISO).
        valid_from: дата начала действия шаблона.
        valid_until: дата окончания или None для бессрочного.
        anchor_date: опорная дата для чётности недель при week_interval=2.
        week_interval: 1 - каждую неделю, 2 - раз в две недели.
        horizon_end: до какой даты считаем (включительно).

    Returns:
        Отсортированный список дат. Пустой, если пересечения периодов нет.

    Raises:
        InvalidDayOfWeekError, NonWorkingDayError, InvalidWeekIntervalError.
    """
    assert_working_day_of_week(day_of_week)

    if week_interval not in (1, 2):
        raise InvalidWeekIntervalError(week_interval)

    # Правый край - самое раннее из конца действия шаблона и горизонта.
    # valid_until может только сузить интервал, поэтому горизонт всегда
    # остаётся верхней границей и защищает от бесконечной генерации.
    period_end = horizon_end if valid_until is None else min(valid_until, horizon_end)

    if valid_from > period_end:
        return []

    current = first_occurrence_on_or_after(valid_from, day_of_week)

    if week_interval == 2:
        # Чётность считается по неделям от опорной даты, а не от valid_from.
        # Поэтому правка даты начала на неделю не переворачивает всю сетку.
        anchor_monday = monday_of_week(anchor_date)
        weeks_from_anchor = (monday_of_week(current) - anchor_monday).days // 7
        if weeks_from_anchor % 2 != 0:
            current += timedelta(days=7)

    step = timedelta(days=7 * week_interval)

    dates: List[date] = []
    while current <= period_end:
        dates.append(current)
        current += step

    return dates


# ==================== ВАЛИДАЦИЯ НАБОРА СЛОТОВ ====================


def find_overlapping_slot_pairs(
    slots: Sequence[Tuple[int, time, int]],
) -> List[Tuple[int, int]]:
    """
    Пары слотов внутри одного шаблона, которые пересекаются по времени.

    Уникальный ключ в БД ловит только полные дубли (тот же день, то же
    время начала). Слоты "вторник 18:00 на 60 минут" и "вторник 18:30 на
    45 минут" формально разные, но описывают одного преподавателя в двух
    местах одновременно - и упрутся в EXCLUDE-констрейнт уже при вставке
    занятий, то есть слишком поздно и с невнятной ошибкой.

    Эта проверка отсекает такой шаблон на этапе сохранения формы.

    Args:
        slots: последовательность кортежей (day_of_week, start_time,
            duration_minutes) в том же порядке, в каком слоты пришли
            из формы.

    Returns:
        Список пар индексов. Пустой список - набор корректен.
    """
    intervals = []
    for day_of_week, start_time, duration_minutes in slots:
        end_time = calculate_end_time(start_time, duration_minutes)
        intervals.append((day_of_week, start_time, end_time))

    overlaps: List[Tuple[int, int]] = []

    for i in range(len(intervals)):
        day_i, start_i, end_i = intervals[i]
        for j in range(i + 1, len(intervals)):
            day_j, start_j, end_j = intervals[j]

            if day_i != day_j:
                continue

            if times_overlap(start_i, end_i, start_j, end_j):
                overlaps.append((i, j))

    return overlaps


__all__ = [
    "SCHEDULE_TZ",
    "WORKING_DAYS",
    "DAY_NAMES",
    "RecurrenceError",
    "LessonCrossesMidnightError",
    "InvalidDayOfWeekError",
    "NonWorkingDayError",
    "InvalidWeekIntervalError",
    "is_working_day",
    "assert_working_day_of_week",
    "today_in_studio_tz",
    "generation_horizon_end",
    "calculate_end_time",
    "duration_minutes_between",
    "times_overlap",
    "monday_of_week",
    "first_occurrence_on_or_after",
    "slot_occurrence_dates",
    "find_overlapping_slot_pairs",
]