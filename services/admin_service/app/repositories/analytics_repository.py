"""
Репозиторий аналитики для админского дашборда.

Все агрегации выполняются на стороне PostgreSQL (GROUP BY, COUNT, AVG,
date_trunc), а не перебором в Python. Дашборд читает готовые числа из
локальных фактовых таблиц admin_service_db: lead_facts,
lead_status_transitions, lesson_facts. Кросс-сервисных запросов нет.

Разделение ответственности:
    - снимок "сейчас" (распределение по статусам, источникам) считается
      из lead_facts;
    - динамика во времени (новые лиды/конверсии по дням) - из дат создания
      в lead_facts и из lead_status_transitions;
    - операционка расписания (занятия, отмены) - из lesson_facts.

Все методы принимают окно дат [date_from, date_to] (включительно по дате).
Окно применяется к бизнес-времени: дате создания лида, дате перехода,
дате занятия - в зависимости от смысла метрики.
"""

import logging
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Float, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal
from app.models.lead_fact import LeadFact
from app.models.lead_status_transition import LeadStatusTransition
from app.models.lesson_fact import LessonFact

logger = logging.getLogger(__name__)


def _start_of_day(d: date) -> datetime:
    """Начало суток в UTC для сравнения с timezone-aware колонками."""
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _end_of_day(d: date) -> datetime:
    """Конец суток в UTC (включительно) для верхней границы окна."""
    return datetime.combine(d, time.max, tzinfo=timezone.utc)


class AnalyticsRepository:
    """Запросы-агрегации по аналитическим проекциям."""

    def __init__(self, session_factory=AdminAsyncSessionLocal):
        self._session_factory = session_factory

    # ==================== ВОРОНКА ЛИДОВ (снимок) ====================

    async def lead_funnel_snapshot(
        self,
        date_from: date,
        date_to: date,
    ) -> Dict[str, int]:
        """
        Распределение лидов по текущему статусу среди лидов, созданных
        в окне [date_from, date_to]. Возвращает {status: count}.

        Это снимок состояния воронки: где сейчас находятся лиды,
        пришедшие за период.
        """
        lo, hi = _start_of_day(date_from), _end_of_day(date_to)
        async with self._session_factory() as session:
            stmt = (
                select(LeadFact.current_status, func.count().label("cnt"))
                .where(
                    and_(
                        LeadFact.lead_created_at >= lo,
                        LeadFact.lead_created_at <= hi,
                    )
                )
                .group_by(LeadFact.current_status)
            )
            rows = (await session.execute(stmt)).all()
            return {status: cnt for status, cnt in rows}

    async def lead_source_breakdown(
        self,
        date_from: date,
        date_to: date,
    ) -> List[Dict[str, Any]]:
        """
        Разрез лидов по источнику за период: сколько всего пришло из
        каждого источника и сколько из них сконвертировано.

        Возвращает список {source, total, converted, conversion_rate}.
        conversion_rate - доля [0..1], converted/total.
        """
        lo, hi = _start_of_day(date_from), _end_of_day(date_to)
        async with self._session_factory() as session:
            converted_sum = func.coalesce(
                func.sum(case((LeadFact.is_converted.is_(True), 1), else_=0)),
                0,
            )
            stmt = (
                select(
                    LeadFact.source,
                    func.count().label("total"),
                    converted_sum.label("converted"),
                )
                .where(
                    and_(
                        LeadFact.lead_created_at >= lo,
                        LeadFact.lead_created_at <= hi,
                    )
                )
                .group_by(LeadFact.source)
                .order_by(func.count().desc())
            )
            rows = (await session.execute(stmt)).all()
            result: List[Dict[str, Any]] = []
            for source, total, converted in rows:
                rate = (converted / total) if total else 0.0
                result.append(
                    {
                        "source": source,
                        "total": int(total),
                        "converted": int(converted),
                        "conversion_rate": round(rate, 4),
                    }
                )
            return result

    async def lost_reasons_breakdown(
        self,
        date_from: date,
        date_to: date,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Топ причин проигрыша среди потерянных лидов за период.
        Возвращает список {reason, count}, отсортированный по убыванию.
        Лиды без указанной причины группируются под reason=None.
        """
        lo, hi = _start_of_day(date_from), _end_of_day(date_to)
        async with self._session_factory() as session:
            stmt = (
                select(LeadFact.lost_reason, func.count().label("cnt"))
                .where(
                    and_(
                        LeadFact.current_status == "lost",
                        LeadFact.lead_created_at >= lo,
                        LeadFact.lead_created_at <= hi,
                    )
                )
                .group_by(LeadFact.lost_reason)
                .order_by(func.count().desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            return [{"reason": reason, "count": int(cnt)} for reason, cnt in rows]

    # ==================== ВОРОНКА ЛИДОВ (динамика) ====================

    async def leads_created_daily(
        self,
        date_from: date,
        date_to: date,
    ) -> List[Dict[str, Any]]:
        """
        Новые лиды по дням за период. Возвращает список {day, count},
        отсортированный по дате. Дни без лидов в результат не попадают -
        заполнение нулями делает сервисный слой (он знает полный диапазон).
        """
        lo, hi = _start_of_day(date_from), _end_of_day(date_to)
        async with self._session_factory() as session:
            day_col = func.date_trunc("day", LeadFact.lead_created_at)
            stmt = (
                select(day_col.label("day"), func.count().label("cnt"))
                .where(
                    and_(
                        LeadFact.lead_created_at >= lo,
                        LeadFact.lead_created_at <= hi,
                    )
                )
                .group_by(day_col)
                .order_by(day_col)
            )
            rows = (await session.execute(stmt)).all()
            return [
                {"day": day.date() if isinstance(day, datetime) else day,
                 "count": int(cnt)}
                for day, cnt in rows
            ]

    async def conversions_daily(
        self,
        date_from: date,
        date_to: date,
    ) -> List[Dict[str, Any]]:
        """
        Конверсии по дням за период - считаем переходы в статус
        'converted' из лога lead_status_transitions по дате перехода.
        Возвращает список {day, count}.

        Используем transitions, а не lead_facts.converted_at, потому что
        это честная "дата события конверсии", а не текущее состояние.
        """
        lo, hi = _start_of_day(date_from), _end_of_day(date_to)
        async with self._session_factory() as session:
            day_col = func.date_trunc("day", LeadStatusTransition.occurred_at)
            stmt = (
                select(day_col.label("day"), func.count().label("cnt"))
                .where(
                    and_(
                        LeadStatusTransition.to_status == "converted",
                        LeadStatusTransition.occurred_at >= lo,
                        LeadStatusTransition.occurred_at <= hi,
                    )
                )
                .group_by(day_col)
                .order_by(day_col)
            )
            rows = (await session.execute(stmt)).all()
            return [
                {"day": day.date() if isinstance(day, datetime) else day,
                 "count": int(cnt)}
                for day, cnt in rows
            ]

    async def avg_time_to_conversion_seconds(
        self,
        date_from: date,
        date_to: date,
    ) -> Optional[float]:
        """
        Среднее время от создания лида до конверсии (в секундах) среди
        лидов, сконвертированных в окне по converted_at. NULL/None, если
        конверсий в окне не было.

        Считаем как AVG(converted_at - lead_created_at) на стороне БД
        через EXTRACT(EPOCH ...).
        """
        lo, hi = _start_of_day(date_from), _end_of_day(date_to)
        async with self._session_factory() as session:
            delta_seconds = func.extract(
                "epoch", LeadFact.converted_at - LeadFact.lead_created_at
            )
            stmt = select(func.avg(delta_seconds)).where(
                and_(
                    LeadFact.converted_at.is_not(None),
                    LeadFact.converted_at >= lo,
                    LeadFact.converted_at <= hi,
                )
            )
            value = await session.scalar(stmt)
            return float(value) if value is not None else None

    # ==================== ОПЕРАЦИОНКА РАСПИСАНИЯ ====================

    async def lesson_totals(
        self,
        date_from: date,
        date_to: date,
    ) -> Dict[str, Any]:
        """
        Сводка по занятиям за период (по дате занятия lesson_date):
        всего занятий, отменённых, доля отмен, сколько переносили.

        Доля отмен = cancelled / total. Перенос отменой не считается -
        в lesson_facts перенос не меняет status и не ставит cancelled_at.
        """
        async with self._session_factory() as session:
            cancelled_sum = func.coalesce(
                func.sum(case((LessonFact.status == "cancelled", 1), else_=0)),
                0,
            )
            rescheduled_sum = func.coalesce(
                func.sum(
                    case((LessonFact.rescheduled_count > 0, 1), else_=0)
                ),
                0,
            )
            stmt = select(
                func.count().label("total"),
                cancelled_sum.label("cancelled"),
                rescheduled_sum.label("rescheduled"),
            ).where(
                and_(
                    LessonFact.lesson_date >= date_from,
                    LessonFact.lesson_date <= date_to,
                )
            )
            row = (await session.execute(stmt)).one()
            total, cancelled, rescheduled = (
                int(row.total),
                int(row.cancelled),
                int(row.rescheduled),
            )
            cancel_rate = (cancelled / total) if total else 0.0
            return {
                "total": total,
                "cancelled": cancelled,
                "rescheduled": rescheduled,
                "cancellation_rate": round(cancel_rate, 4),
            }

    async def lessons_per_teacher(
        self,
        date_from: date,
        date_to: date,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Занятия по преподавателям за период (по дате занятия):
        всего проведённых записей и сколько из них отменено.

        Возвращает список {teacher_id, total, cancelled}, отсортированный
        по total убыванию. Имена преподавателей подставляет сервисный слой
        из users_cache - репозиторий оперирует только id.
        """
        async with self._session_factory() as session:
            cancelled_sum = func.coalesce(
                func.sum(case((LessonFact.status == "cancelled", 1), else_=0)),
                0,
            )
            stmt = (
                select(
                    LessonFact.teacher_id,
                    func.count().label("total"),
                    cancelled_sum.label("cancelled"),
                )
                .where(
                    and_(
                        LessonFact.lesson_date >= date_from,
                        LessonFact.lesson_date <= date_to,
                    )
                )
                .group_by(LessonFact.teacher_id)
                .order_by(func.count().desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            return [
                {
                    "teacher_id": int(teacher_id),
                    "total": int(total),
                    "cancelled": int(cancelled),
                }
                for teacher_id, total, cancelled in rows
            ]

    async def lessons_daily(
        self,
        date_from: date,
        date_to: date,
    ) -> List[Dict[str, Any]]:
        """
        Занятия по дням за период (по дате занятия lesson_date).
        Возвращает список {day, total, cancelled}.
        """
        async with self._session_factory() as session:
            cancelled_sum = func.coalesce(
                func.sum(case((LessonFact.status == "cancelled", 1), else_=0)),
                0,
            )
            stmt = (
                select(
                    LessonFact.lesson_date.label("day"),
                    func.count().label("total"),
                    cancelled_sum.label("cancelled"),
                )
                .where(
                    and_(
                        LessonFact.lesson_date >= date_from,
                        LessonFact.lesson_date <= date_to,
                    )
                )
                .group_by(LessonFact.lesson_date)
                .order_by(LessonFact.lesson_date)
            )
            rows = (await session.execute(stmt)).all()
            return [
                {"day": day, "total": int(total), "cancelled": int(cancelled)}
                for day, total, cancelled in rows
            ]


analytics_repository = AnalyticsRepository()