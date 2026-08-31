"""
Pydantic schemas для Lessons
"""

from typing import Optional, List, Dict
from datetime import date, time, datetime
from pydantic import BaseModel, Field, field_validator

from app.domain.recurrence import WORKING_DAYS


class LessonCreate(BaseModel):
    """Схема создания разового занятия"""

    studio_id: int = Field(..., description="ID студии")
    teacher_id: int = Field(..., description="ID преподавателя")
    classroom_id: Optional[int] = Field(None, description="ID кабинета (NULL для онлайн)")

    lesson_date: date = Field(..., description="Дата занятия")
    start_time: time = Field(..., description="Время начала")
    duration_minutes: int = Field(60, ge=15, le=480, description="Длительность в минутах")

    student_ids: List[int] = Field(default_factory=list, description="Список ID учеников")
    notes: Optional[str] = Field(None, max_length=1000, description="Заметки")

    @field_validator("lesson_date")
    @classmethod
    def validate_working_day(cls, value: date) -> date:
        """
        Занятие нельзя поставить на нерабочий день.

        Дело не в формальном запрете: календарь рисует только рабочую
        неделю, поэтому занятие на нерабочий день оказалось бы невидимым.
        Оно существовало бы в базе, занимало кабинет и конфликтовало
        с другими занятиями, не показываясь нигде в интерфейсе.
        """
        if value.isoweekday() not in WORKING_DAYS:
            raise ValueError("В этот день недели студия не работает")
        return value


class LessonUpdate(BaseModel):
    """
    Схема обновления занятия.

    Только редактирование расписания и метаданных. Смена статуса и
    отмена идут через отдельные эндпоинты:
        - POST /lessons/{id}/cancel
        - POST /lessons/{id}/restore
        - POST /lessons/{id}/complete
        - POST /lessons/{id}/mark-missed
    """

    classroom_id: Optional[int] = None
    lesson_date: Optional[date] = None
    start_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=15, le=480)
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("lesson_date")
    @classmethod
    def validate_working_day(cls, value: Optional[date]) -> Optional[date]:
        """Перенести занятие на нерабочий день тоже нельзя."""
        if value is not None and value.isoweekday() not in WORKING_DAYS:
            raise ValueError("В этот день недели студия не работает")
        return value


class LessonStudentInfo(BaseModel):
    """Информация об ученике на занятии"""

    student_id: int
    attendance_status: str

    model_config = {"from_attributes": True}


class LessonResponse(BaseModel):
    """Схема ответа с занятием"""

    id: int
    studio_id: int
    teacher_id: int
    classroom_id: Optional[int]
    recurring_pattern_id: Optional[int]

    lesson_date: date
    start_time: time
    end_time: time
    status: str

    notes: Optional[str]
    cancellation_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Дополнительные поля
    students: List[LessonStudentInfo] = Field(default_factory=list)
    is_recurring: bool = Field(False, description="Создано из шаблона")

    model_config = {"from_attributes": True}


class LessonListResponse(BaseModel):
    """Схема списка занятий"""

    lessons: List[LessonResponse]
    total: int


class LessonWithDetails(LessonResponse):
    """Расширенная информация о занятии"""

    teacher_name: Optional[str] = None
    student_names: List[str] = Field(default_factory=list)
    classroom_name: Optional[str] = None
    studio_name: Optional[str] = None


class LessonCancelRequest(BaseModel):
    """Тело запроса POST /lessons/{id}/cancel."""

    reason: Optional[str] = Field(default=None, max_length=500)


class LessonCompleteRequest(BaseModel):
    """
    Тело запроса POST /lessons/{id}/complete.

    attendance - посещаемость поимённо, {student_id: статус}.
    Не передана - все считаются присутствовавшими.

    Раздельная посещаемость нужна, потому что "занятие не состоялось"
    и "один ученик не пришёл" - разные события. Для группового занятия
    второе не должно отменять первое.
    """

    attendance: Optional[Dict[int, str]] = Field(
        default=None,
        description="Посещаемость по ученикам: attended или missed",
    )

    @field_validator("attendance")
    @classmethod
    def validate_attendance(cls, value):
        if value is None:
            return value
        allowed = {"attended", "missed"}
        for student_id, item in value.items():
            if item not in allowed:
                raise ValueError(
                    f"Недопустимый статус посещения '{item}' "
                    f"для ученика {student_id}. Ожидается attended или missed"
                )
        return value