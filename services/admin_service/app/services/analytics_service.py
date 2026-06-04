"""
Analytics Dashboard Service.

Оркеструет AnalyticsRepository и собирает цельный ответ дашборда:
    - вызывает агрегации репозитория;
    - заполняет пропущенные дни нулями (репозиторий возвращает только дни
      с данными, а график должен быть непрерывным);
    - переводит секунды в часы для человекочитаемости;
    - подставляет имена преподавателей из users_cache (один запрос по
      списку id, без N+1);
    - выставляет data_complete по флагу наполненности проекции.

Никаких сырых списков и пересчёта в Python: числа приходят из БД готовыми,
сервис только досабирает их в форму ответа.
"""

import logging
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import func, select

from app.database.connection import AdminAsyncSessionLocal
from app.models.lead_fact import LeadFact
from app.models.lesson_fact import LessonFact
from app.models.user_cache import UserCache
from app.repositories.analytics_repository import analytics_repository
from app.schemas.analytics import (
    AnalyticsDashboardResponse,
    AnalyticsPeriod,
    DailyPoint,
    FunnelStage,
    LeadsAnalytics,
    LessonDailyPoint,
    LessonsAnalytics,
    LostReasonItem,
    SourceBreakdownItem,
    TeacherLoadItem,
)

logger = logging.getLogger(__name__)


# Канонический порядок этапов воронки для стабильного отображения.
# Статусы, которых нет в снимке, выводятся с нулём; неизвестные статусы
# (если CRM добавит новый) добавляются в конец.
_FUNNEL_ORDER = [
    "new",
    "contacted",
    "trial_scheduled",
    "trial_attended",
    "converted",
    "lost",
]


class AnalyticsService:
    """Сборка ответа аналитического дашборда."""

    def __init__(self, repository=analytics_repository):
        self._repo = repository

    async def get_dashboard(
        self,
        date_from: date,
        date_to: date,
    ) -> AnalyticsDashboardResponse:
        """Собрать полный ответ дашборда за окно [date_from, date_to]."""
        days = (date_to - date_from).days + 1
        period = AnalyticsPeriod(
            date_from=date_from,
            date_to=date_to,
            days=days,
        )

        leads = await self._build_leads(date_from, date_to)
        lessons = await self._build_lessons(date_from, date_to)
        data_complete = await self._is_projection_populated()

        return AnalyticsDashboardResponse(
            period=period,
            leads=leads,
            lessons=lessons,
            data_complete=data_complete,
        )

    # ==================== ЛИДЫ ====================

    async def _build_leads(
        self,
        date_from: date,
        date_to: date,
    ) -> LeadsAnalytics:
        funnel_snapshot = await self._repo.lead_funnel_snapshot(date_from, date_to)
        by_source = await self._repo.lead_source_breakdown(date_from, date_to)
        lost = await self._repo.lost_reasons_breakdown(date_from, date_to)
        created_daily = await self._repo.leads_created_daily(date_from, date_to)
        conv_daily = await self._repo.conversions_daily(date_from, date_to)
        avg_seconds = await self._repo.avg_time_to_conversion_seconds(
            date_from, date_to
        )

        total_created = sum(funnel_snapshot.values())
        total_converted = sum(p["count"] for p in conv_daily)
        overall_rate = (
            (total_converted / total_created) if total_created else 0.0
        )
        avg_hours = (avg_seconds / 3600.0) if avg_seconds is not None else None

        return LeadsAnalytics(
            total_created=total_created,
            total_converted=total_converted,
            overall_conversion_rate=round(overall_rate, 4),
            avg_time_to_conversion_hours=(
                round(avg_hours, 2) if avg_hours is not None else None
            ),
            funnel=self._order_funnel(funnel_snapshot),
            by_source=[SourceBreakdownItem(**item) for item in by_source],
            lost_reasons=[LostReasonItem(**item) for item in lost],
            created_daily=self._fill_daily(created_daily, date_from, date_to),
            conversions_daily=self._fill_daily(conv_daily, date_from, date_to),
        )

    def _order_funnel(self, snapshot: Dict[str, int]) -> List[FunnelStage]:
        """Упорядочить этапы воронки канонически, дополнив нулями."""
        stages: List[FunnelStage] = []
        seen = set()
        for status in _FUNNEL_ORDER:
            stages.append(FunnelStage(status=status, count=snapshot.get(status, 0)))
            seen.add(status)
        # Неизвестные статусы (на случай эволюции CRM) - в конец.
        for status, count in snapshot.items():
            if status not in seen:
                stages.append(FunnelStage(status=status, count=count))
        return stages

    # ==================== ЗАНЯТИЯ ====================

    async def _build_lessons(
        self,
        date_from: date,
        date_to: date,
    ) -> LessonsAnalytics:
        totals = await self._repo.lesson_totals(date_from, date_to)
        per_teacher = await self._repo.lessons_per_teacher(date_from, date_to)
        daily = await self._repo.lessons_daily(date_from, date_to)

        teacher_ids = [item["teacher_id"] for item in per_teacher]
        names = await self._resolve_teacher_names(teacher_ids)

        by_teacher = [
            TeacherLoadItem(
                teacher_id=item["teacher_id"],
                teacher_name=names.get(item["teacher_id"]),
                total=item["total"],
                cancelled=item["cancelled"],
            )
            for item in per_teacher
        ]

        lessons_daily = self._fill_lesson_daily(daily, date_from, date_to)

        return LessonsAnalytics(
            total=totals["total"],
            cancelled=totals["cancelled"],
            rescheduled=totals["rescheduled"],
            cancellation_rate=totals["cancellation_rate"],
            by_teacher=by_teacher,
            lessons_daily=lessons_daily,
        )

    async def _resolve_teacher_names(
        self,
        teacher_ids: List[int],
    ) -> Dict[int, str]:
        """
        Достать имена преподавателей из users_cache одним запросом.
        Возвращает {id: "Имя Фамилия"}. Отсутствующие в кэше id просто
        не попадут в словарь - тогда teacher_name останется None.
        """
        if not teacher_ids:
            return {}
        async with AdminAsyncSessionLocal() as session:
            stmt = select(
                UserCache.id, UserCache.first_name, UserCache.last_name
            ).where(UserCache.id.in_(teacher_ids))
            rows = (await session.execute(stmt)).all()
            return {
                uid: f"{first or ''} {last or ''}".strip()
                for uid, first, last in rows
            }

    # ==================== ХЕЛПЕРЫ ВРЕМЕННЫХ РЯДОВ ====================

    def _date_range(self, date_from: date, date_to: date) -> List[date]:
        """Все даты окна включительно."""
        span = (date_to - date_from).days
        return [date_from + timedelta(days=i) for i in range(span + 1)]

    def _fill_daily(
        self,
        points: List[Dict],
        date_from: date,
        date_to: date,
    ) -> List[DailyPoint]:
        """Дополнить ряд {day, count} нулями для дней без данных."""
        by_day = {p["day"]: p["count"] for p in points}
        return [
            DailyPoint(day=d, count=by_day.get(d, 0))
            for d in self._date_range(date_from, date_to)
        ]

    def _fill_lesson_daily(
        self,
        points: List[Dict],
        date_from: date,
        date_to: date,
    ) -> List[LessonDailyPoint]:
        """Дополнить ряд занятий {day, total, cancelled} нулями."""
        by_day = {p["day"]: p for p in points}
        result: List[LessonDailyPoint] = []
        for d in self._date_range(date_from, date_to):
            p = by_day.get(d)
            result.append(
                LessonDailyPoint(
                    day=d,
                    total=p["total"] if p else 0,
                    cancelled=p["cancelled"] if p else 0,
                )
            )
        return result

    # ==================== НАПОЛНЕННОСТЬ ПРОЕКЦИИ ====================

    async def _is_projection_populated(self) -> bool:
        """
        Эвристика "данные полны": в проекции есть хотя бы один факт.
        Пустые таблицы означают, что backfill ещё не прогоняли и/или
        событий не было - дашборд покажет предупреждение.
        """
        async with AdminAsyncSessionLocal() as session:
            has_lead = await session.scalar(select(func.count(LeadFact.id)).limit(1))
            has_lesson = await session.scalar(
                select(func.count(LessonFact.id)).limit(1)
            )
            return bool((has_lead or 0) > 0 or (has_lesson or 0) > 0)


analytics_service = AnalyticsService()