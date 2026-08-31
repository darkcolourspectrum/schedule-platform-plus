"""
Трансляция ошибок целостности БД в доменные исключения.

После блока 1 инварианты расписания живут в базе: уникальность занятия
внутри слота, порядок времени, допустимые статусы и два EXCLUDE-констрейнта
на пересечение по кабинету и преподавателю.

Это правильно - база не даёт себя обмануть даже при гонке двух запросов.
Но у такой защиты есть побочный эффект: нарушение прилетает как
IntegrityError, и без перевода пользователь увидит 500 и пустое тело
ответа вместо "кабинет занят".

Модуль решает ровно эту задачу: по имени нарушенного констрейнта подобрать
доменное исключение с понятным текстом.

Когда срабатывает:
    Штатный путь - сервис заранее спросил ConflictService и вернул 409 сам.
    Сюда попадают случаи, которые проверка увидеть не могла: два
    параллельных запроса на один слот, или расхождение между кодом
    проверки и констрейнтом. То есть это страховка, а не основной сценарий.
"""

import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    ClassroomConflictException,
    DuplicateLessonException,
    InvalidTimeRangeException,
    ScheduleServiceException,
    StudentConflictException,
    TeacherConflictException,
)

logger = logging.getLogger(__name__)


def extract_constraint_name(exc: IntegrityError) -> Optional[str]:
    """
    Достать имя нарушенного констрейнта из исключения.

    Драйвер asyncpg кладёт имя в атрибут constraint_name, но SQLAlchemy
    оборачивает исходную ошибку в свой класс, и глубина обёртки зависит
    от версии. Поэтому сначала обходим цепочку исключений в поисках
    атрибута, а если не нашли - ищем имя в тексте: PostgreSQL всегда
    включает его в сообщение.
    """
    current = exc
    seen = 0

    while current is not None and seen < 5:
        name = getattr(current, "constraint_name", None)
        if name:
            return str(name)
        current = getattr(current, "orig", None) or getattr(
            current, "__cause__", None
        )
        seen += 1

    message = str(exc)
    for known in _CONSTRAINT_TRANSLATORS:
        if known in message:
            return known

    return None


def translate_integrity_error(
    exc: IntegrityError,
) -> Optional[ScheduleServiceException]:
    """
    Перевести IntegrityError в доменное исключение.

    Returns:
        Доменное исключение, если констрейнт распознан.
        None, если нет - тогда вызывающий код должен пробросить исходную
        ошибку дальше, а не глотать её. Неизвестное нарушение целостности
        это баг, и он должен быть шумным.
    """
    constraint = extract_constraint_name(exc)

    if not constraint:
        logger.error(
            "IntegrityError without recognizable constraint name: %s", exc
        )
        return None

    translator = _CONSTRAINT_TRANSLATORS.get(constraint)

    if translator is None:
        logger.error(
            "IntegrityError on unmapped constraint '%s': %s", constraint, exc
        )
        return None

    logger.warning(
        "Constraint '%s' violated - translated to domain exception. "
        "Это значит, что проверка конфликтов не увидела проблему заранее "
        "(гонка запросов или расхождение проверки с констрейнтом)",
        constraint,
    )

    return translator()


# Соответствие имён из миграции b7c4e2f19a03 доменным ошибкам.
# При добавлении констрейнта в БД добавляй строку сюда, иначе
# пользователь получит 500 вместо осмысленного ответа.
_CONSTRAINT_TRANSLATORS = {
    "uq_lesson_slot_date": lambda: DuplicateLessonException(),
    "excl_lesson_classroom_overlap": lambda: ClassroomConflictException(),
    "excl_lesson_teacher_overlap": lambda: TeacherConflictException(),
    "ck_lesson_time_order": lambda: InvalidTimeRangeException(
        "Занятие должно заканчиваться позже, чем начинается, "
        "и не выходить за пределы суток"
    ),
    "ck_lesson_status": lambda: InvalidTimeRangeException(
        "Недопустимый статус занятия"
    ),
    "ck_pattern_slot_day_of_week": lambda: InvalidTimeRangeException(
        "День недели должен быть от 1 (понедельник) до 7 (воскресенье)"
    ),
    "ck_pattern_slot_duration": lambda: InvalidTimeRangeException(
        "Длительность занятия должна быть от 1 до 480 минут"
    ),
    "ck_pattern_week_interval": lambda: InvalidTimeRangeException(
        "Периодичность может быть только еженедельной или раз в две недели"
    ),
    "ck_pattern_valid_range": lambda: InvalidTimeRangeException(
        "Дата окончания не может быть раньше даты начала"
    ),
    "uq_pattern_slot_day_time": lambda: DuplicateLessonException(
        "В шаблоне уже есть слот на этот день и время"
    ),
    "uq_lesson_student": lambda: DuplicateLessonException(
        "Ученик уже добавлен на это занятие"
    ),
    "uq_pattern_student": lambda: DuplicateLessonException(
        "Ученик уже добавлен в этот шаблон"
    ),
}


__all__ = [
    "extract_constraint_name",
    "translate_integrity_error",
]