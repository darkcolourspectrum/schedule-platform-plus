"""
Схемы шаблонов повторяющихся занятий.

Файл переписан под модель со слотами. Прежние схемы описывали шаблон
как "один день недели плюс одно время", теперь это шапка (кто, с кем,
в какой период, с какой периодичностью) и набор слотов (когда именно).

Валидация делается здесь, а не в сервисе, намеренно: ошибка в форме
должна вернуться как 422 с указанием поля до того, как запрос дойдёт
до БД. Проверяется то, что нельзя выразить констрейнтом:
    - день недели входит в рабочие дни студии;
    - слоты внутри шаблона не пересекаются между собой;
    - ни один слот не выходит за полночь;
    - период действия непустой.
"""

from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.recurrence import (
    DAY_NAMES,
    WORKING_DAYS,
    LessonCrossesMidnightError,
    calculate_end_time,
    find_overlapping_slot_pairs,
)


# ==================== СЛОТЫ ====================


class RecurringPatternSlotCreate(BaseModel):
    """Одно правило повторения: день недели, время, длительность, кабинет."""

    day_of_week: int = Field(
        ..., ge=1, le=7, description="1=Пн, 2=Вт, ..., 7=Вс"
    )
    start_time: time = Field(..., description="Время начала занятия")
    duration_minutes: int = Field(
        60, ge=15, le=480, description="Длительность в минутах"
    )
    classroom_id: Optional[int] = Field(
        None, description="Кабинет, NULL для онлайн-занятия"
    )

    @field_validator("day_of_week")
    @classmethod
    def validate_working_day(cls, value: int) -> int:
        """
        Слот не может стоять на нерабочий день.

        Иначе занятия создались бы, заняли кабинет и участвовали в
        конфликтах, но не показались бы в календаре: он рисует только
        рабочую неделю.
        """
        if value not in WORKING_DAYS:
            raise ValueError(
                f"{DAY_NAMES[value].capitalize()} - нерабочий день студии"
            )
        return value


class RecurringPatternSlotResponse(BaseModel):
    """Слот в ответе. end_time считается, в БД не хранится."""

    id: int
    day_of_week: int
    day_name: str
    start_time: time
    end_time: time
    duration_minutes: int
    classroom_id: Optional[int]

    model_config = {"from_attributes": True}


# ==================== ОБЩАЯ ВАЛИДАЦИЯ ====================


class _PatternSlotsMixin(BaseModel):
    """Проверки, общие для создания, обновления и предпросмотра."""

    @staticmethod
    def _validate_slot_set(slots: List[RecurringPatternSlotCreate]) -> None:
        """
        Слоты валидны как набор.

        Пересечение слотов внутри шаблона уникальным ключом не ловится:
        "вторник 18:00 на час" и "вторник 18:30 на 45 минут" - формально
        разные строки, но один преподаватель в двух местах. Такой шаблон
        упёрся бы в EXCLUDE-констрейнт только при вставке занятий, то есть
        после сохранения и с невнятной ошибкой.
        """
        for index, slot in enumerate(slots):
            try:
                calculate_end_time(slot.start_time, slot.duration_minutes)
            except LessonCrossesMidnightError:
                raise ValueError(
                    f"Слот {index + 1} ({DAY_NAMES[slot.day_of_week]}, "
                    f"{slot.start_time.strftime('%H:%M')}) выходит за пределы "
                    f"суток. Уменьши длительность или сдвинь время начала"
                )

        overlaps = find_overlapping_slot_pairs(
            [(s.day_of_week, s.start_time, s.duration_minutes) for s in slots]
        )

        if overlaps:
            first, second = overlaps[0]
            slot_a = slots[first]
            slot_b = slots[second]
            raise ValueError(
                f"Слоты пересекаются по времени: "
                f"{DAY_NAMES[slot_a.day_of_week]} "
                f"{slot_a.start_time.strftime('%H:%M')} и "
                f"{DAY_NAMES[slot_b.day_of_week]} "
                f"{slot_b.start_time.strftime('%H:%M')}. "
                f"Преподаватель не может вести два занятия одновременно"
            )


# ==================== СОЗДАНИЕ ====================


class RecurringPatternCreate(_PatternSlotsMixin):
    """Создание шаблона."""

    studio_id: int = Field(..., description="ID студии")
    teacher_id: int = Field(..., description="ID преподавателя")

    valid_from: date = Field(..., description="Действует с")
    valid_until: Optional[date] = Field(
        None, description="Действует до, NULL = бессрочно"
    )

    week_interval: int = Field(
        1, ge=1, le=2, description="1 = каждую неделю, 2 = раз в две недели"
    )

    slots: List[RecurringPatternSlotCreate] = Field(
        ...,
        min_length=1,
        max_length=7,
        description="Дни и время. Минимум один, максимум семь",
    )

    student_ids: List[int] = Field(default_factory=list)
    notes: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def validate_pattern(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError(
                "Дата окончания не может быть раньше даты начала"
            )
        self._validate_slot_set(self.slots)
        return self


# ==================== ОБНОВЛЕНИЕ ====================


class RecurringPatternUpdate(_PatternSlotsMixin):
    """
    Обновление шаблона.

    slots передаётся целиком или не передаётся вовсе. Частичное изменение
    одного слота не поддерживается сознательно: набор слотов - это единое
    правило, и менять его надо целиком, чтобы предпросмотр показывал
    итоговую картину, а не промежуточную.
    """

    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    week_interval: Optional[int] = Field(None, ge=1, le=2)
    is_active: Optional[bool] = None
    slots: Optional[List[RecurringPatternSlotCreate]] = Field(
        None, min_length=1, max_length=7
    )
    student_ids: Optional[List[int]] = None
    notes: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def validate_pattern(self):
        if (
            self.valid_from
            and self.valid_until
            and self.valid_until < self.valid_from
        ):
            raise ValueError(
                "Дата окончания не может быть раньше даты начала"
            )
        if self.slots is not None:
            self._validate_slot_set(self.slots)
        return self


# ==================== ОТВЕТЫ ====================


class RecurringPatternResponse(BaseModel):
    """Шаблон в ответе."""

    id: int
    studio_id: int
    teacher_id: int

    valid_from: date
    valid_until: Optional[date]
    anchor_date: date
    week_interval: int
    is_active: bool

    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    slots: List[RecurringPatternSlotResponse] = Field(default_factory=list)
    student_ids: List[int] = Field(default_factory=list)
    generated_lessons_count: int = 0

    model_config = {"from_attributes": True}


class RecurringPatternListResponse(BaseModel):
    """Список шаблонов."""

    patterns: List[RecurringPatternResponse]
    total: int


# ==================== ПРЕДПРОСМОТР ====================


class PreviewConflictItem(BaseModel):
    """
    Одна причина, по которой занятие не будет создано.

    subject_id - id ресурса: кабинета, преподавателя или ученика.
    Имена подставляет фронт, у него уже есть справочники.
    """

    lesson_date: date
    start_time: time
    end_time: time
    kind: str = Field(..., description="classroom, teacher или student")
    subject_id: int
    classroom_id: Optional[int] = None
    message: str


class RecurringPatternPreviewRequest(RecurringPatternCreate):
    """
    Запрос предпросмотра. Та же форма, что и создание.

    pattern_id указывается при предпросмотре изменений уже существующего
    шаблона - тогда его собственные занятия не считаются конфликтом.
    """

    pattern_id: Optional[int] = Field(
        None, description="ID редактируемого шаблона, если это правка"
    )


class RecurringPatternPreviewResponse(BaseModel):
    """
    Что произойдёт при сохранении. В БД ничего не записано.

    Числа считаются тем же кодом, что и реальная генерация, поэтому
    will_create_count совпадёт с количеством созданных занятий.
    """

    will_create_count: int
    already_exists_count: int
    blocked_count: int
    horizon_end: date
    dates: List[date] = Field(
        default_factory=list, description="Даты занятий к созданию"
    )
    conflicts: List[PreviewConflictItem] = Field(default_factory=list)


# ==================== РЕЗУЛЬТАТ ГЕНЕРАЦИИ ====================


class PatternGenerationSummary(BaseModel):
    """Итог генерации, прикладывается к ответу создания и обновления."""

    created_count: int = 0
    already_existed_count: int = 0
    blocked_count: int = 0
    batch_id: Optional[str] = Field(
        None, description="ID прогона, по нему работает откат"
    )
    conflicts: List[PreviewConflictItem] = Field(default_factory=list)


class RecurringPatternWithGeneration(BaseModel):
    """Шаблон плюс результат генерации."""

    pattern: RecurringPatternResponse
    generation: PatternGenerationSummary