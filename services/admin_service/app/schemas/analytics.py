"""
Pydantic-схемы ответов аналитического дашборда.

Контракт между Admin Service и фронтендом. Все суммы/доли уже посчитаны
на бэке - фронт только отображает. Доли (rate) приходят как доли [0..1];
форматирование в проценты - забота фронта.

Структура ответа GET /dashboard/analytics:
    - period: какое окно дат охватывает ответ;
    - leads: блок воронки лидов (снимок + разрезы + динамика);
    - lessons: блок операционки расписания (сводка + по преподавателям +
      динамика).
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


# ==================== ОБЩЕЕ ====================


class AnalyticsPeriod(BaseModel):
    """Окно дат, за которое посчитана аналитика (включительно)."""

    date_from: date
    date_to: date
    days: int = Field(..., description="Число дней в окне, включительно")


class DailyPoint(BaseModel):
    """Точка временного ряда: значение за конкретный день."""

    day: date
    count: int


class LessonDailyPoint(BaseModel):
    """Точка ряда занятий за день: всего и сколько отменено."""

    day: date
    total: int
    cancelled: int


# ==================== ВОРОНКА ЛИДОВ ====================


class FunnelStage(BaseModel):
    """Один этап воронки: статус и сколько лидов в нём сейчас."""

    status: str
    count: int


class SourceBreakdownItem(BaseModel):
    """Разрез по источнику лида с конверсией."""

    source: str
    total: int
    converted: int
    conversion_rate: float = Field(..., description="Доля [0..1]: converted/total")


class LostReasonItem(BaseModel):
    """Причина проигрыша и число потерянных по ней лидов."""

    reason: Optional[str] = Field(None, description="None = причина не указана")
    count: int


class LeadsAnalytics(BaseModel):
    """Аналитика воронки лидов за период."""

    total_created: int = Field(..., description="Всего новых лидов за период")
    total_converted: int = Field(
        ..., description="Всего конверсий за период (по дате конверсии)"
    )
    overall_conversion_rate: float = Field(
        ..., description="Доля [0..1]: конверсии / созданные за период"
    )
    avg_time_to_conversion_hours: Optional[float] = Field(
        None,
        description="Среднее время лид->конверсия в часах; None если конверсий нет",
    )

    # Снимок и разрезы.
    funnel: List[FunnelStage] = Field(default_factory=list)
    by_source: List[SourceBreakdownItem] = Field(default_factory=list)
    lost_reasons: List[LostReasonItem] = Field(default_factory=list)

    # Динамика (по дням, дни без данных заполнены нулями).
    created_daily: List[DailyPoint] = Field(default_factory=list)
    conversions_daily: List[DailyPoint] = Field(default_factory=list)


# ==================== ОПЕРАЦИОНКА РАСПИСАНИЯ ====================


class TeacherLoadItem(BaseModel):
    """
    Нагрузка преподавателя за период.

    Намеренно НЕ называется "загрузка в процентах": система не хранит
    рабочее время преподавателя, поэтому честная метрика - количество
    занятий и сколько из них отменено, а не доля занятого времени.
    """

    teacher_id: int
    teacher_name: Optional[str] = Field(
        None, description="Имя из users_cache; None если не найдено"
    )
    total: int
    cancelled: int


class LessonsAnalytics(BaseModel):
    """Операционная аналитика расписания за период."""

    total: int = Field(..., description="Всего занятий за период")
    cancelled: int = Field(..., description="Из них отменено")
    rescheduled: int = Field(
        ..., description="Сколько занятий переносили (перенос != отмена)"
    )
    cancellation_rate: float = Field(
        ..., description="Доля [0..1]: cancelled/total"
    )

    by_teacher: List[TeacherLoadItem] = Field(default_factory=list)
    lessons_daily: List[LessonDailyPoint] = Field(default_factory=list)


# ==================== КОРНЕВОЙ ОТВЕТ ====================


class AnalyticsDashboardResponse(BaseModel):
    """Полный ответ аналитического дашборда."""

    period: AnalyticsPeriod
    leads: LeadsAnalytics
    lessons: LessonsAnalytics

    # Признак "данные могут быть неполны": проекция наполняется из событий
    # с момента запуска consumer'ов. Если backfill ещё не прогоняли, часть
    # истории отсутствует. Фронт может показать предупреждение.
    data_complete: bool = Field(
        True,
        description="False если аналитическая проекция ещё не наполнена backfill'ом",
    )