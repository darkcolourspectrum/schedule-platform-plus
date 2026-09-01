from app.messaging.outbox import (
    LessonCreatedPayload,
    LessonCancelledPayload,
    LessonRescheduledPayload,
    GeneratedLessonItem,
    GenerationLessonsCreatedPayload,
    GenerationLessonsDeletedPayload,
    PatternSlotItem,
    PatternSchedulePayload,
    PatternUnassignedPayload,
    DELETION_REASON_PATTERN_UPDATED,
    DELETION_REASON_PATTERN_DELETED,
    DELETION_REASON_BATCH_ROLLED_BACK,
    record_lesson_created,
    record_lesson_cancelled,
    record_lesson_rescheduled,
    record_generation_lessons_created,
    record_generation_lessons_deleted,
    record_pattern_assigned,
    record_pattern_changed,
    record_pattern_unassigned,
)

__all__ = [
    # Outbox payloads: разовые занятия
    "LessonCreatedPayload",
    "LessonCancelledPayload",
    "LessonRescheduledPayload",

    # Outbox payloads: генерация из шаблонов
    "GeneratedLessonItem",
    "GenerationLessonsCreatedPayload",
    "GenerationLessonsDeletedPayload",

    # Outbox payloads: назначение шаблонов ученикам
    "PatternSlotItem",
    "PatternSchedulePayload",
    "PatternUnassignedPayload",

    # Причины удаления занятий
    "DELETION_REASON_PATTERN_UPDATED",
    "DELETION_REASON_PATTERN_DELETED",
    "DELETION_REASON_BATCH_ROLLED_BACK",

    # Outbox record-функции
    "record_lesson_created",
    "record_lesson_cancelled",
    "record_lesson_rescheduled",
    "record_generation_lessons_created",
    "record_generation_lessons_deleted",
    "record_pattern_assigned",
    "record_pattern_changed",
    "record_pattern_unassigned",
]