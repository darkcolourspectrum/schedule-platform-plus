"""
Статусы занятия и посещения - единый словарь для всего сервиса.

Строки статусов были рассыпаны по коду десятками литералов: сервис,
репозитории и генератор шаблонов сравнивали их каждый по-своему.
Опечатка в любом из мест не ловилась ничем - сравнение просто молча
возвращало False, и занятие тихо не попадало в выборку.

Здесь же зафиксирована разница между двумя уровнями. Статус занятия
отвечает, что было с занятием целиком. Статус посещения - что было
с конкретным учеником. Для группового занятия это разные вещи: занятие
состоялось, а двое учеников не пришли.
"""


class LessonStatus:
    """Статус занятия. Значения совпадают с CHECK ck_lesson_status."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"
    TEACHER_MISSED = "teacher_missed"

    ALL = (SCHEDULED, COMPLETED, CANCELLED, MISSED, TEACHER_MISSED)

    # Занятие стало историей: ни перенести, ни удалить. Список один на
    # весь сервис - иначе он расходится по местам употребления при
    # добавлении нового статуса.
    FINAL = (COMPLETED, MISSED, TEACHER_MISSED)


class AttendanceStatus:
    """Статус посещения одного ученика."""

    SCHEDULED = "scheduled"
    ATTENDED = "attended"
    MISSED = "missed"
    CANCELLED = "cancelled"

    ALL = (SCHEDULED, ATTENDED, MISSED, CANCELLED)