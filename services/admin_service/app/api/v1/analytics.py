"""
Analytics Dashboard API.

Эндпоинт отдаёт агрегированную аналитику для админского дашборда:
воронку лидов, конверсию, источники, операционку расписания - всё
посчитано на бэке из локальной аналитической проекции.

Период задаётся одним из двух способов:
    - быстрый: ?days=7|30|90 (по умолчанию 30) - окно "последние N дней"
      по сегодняшнюю дату включительно;
    - точный: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD - произвольное окно.
Если заданы обе формы, приоритет у явных дат.

Доступ только администраторам (get_current_admin).
"""

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_admin
from app.schemas.analytics import AnalyticsDashboardResponse
from app.services.analytics_service import analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Admin Dashboard"])


# Допустимые значения быстрого пресета периода (дни).
_ALLOWED_PRESETS = {7, 30, 90}

# Защитный предел на ширину произвольного окна, чтобы тяжёлый запрос
# не положил БД. Год с запасом.
_MAX_WINDOW_DAYS = 400


def _resolve_period(
    days: int,
    date_from: Optional[date],
    date_to: Optional[date],
) -> tuple[date, date]:
    """
    Вычислить окно [date_from, date_to] из параметров запроса.

    Явные даты имеют приоритет над пресетом days. Валидирует порядок дат
    и ширину окна.
    """
    if date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="date_from и date_to нужно задавать вместе",
            )
        if date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="date_from не может быть позже date_to",
            )
        if (date_to - date_from).days + 1 > _MAX_WINDOW_DAYS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Окно не может превышать {_MAX_WINDOW_DAYS} дней",
            )
        return date_from, date_to

    if days not in _ALLOWED_PRESETS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"days должен быть одним из {sorted(_ALLOWED_PRESETS)}",
        )
    today = date.today()
    return today - timedelta(days=days - 1), today


@router.get("/analytics", response_model=AnalyticsDashboardResponse)
async def get_analytics_dashboard(
    days: int = Query(
        30,
        description="Быстрый период: 7, 30 или 90 дней (если не заданы даты)",
    ),
    date_from: Optional[date] = Query(
        None, description="Начало окна (YYYY-MM-DD), вместе с date_to"
    ),
    date_to: Optional[date] = Query(
        None, description="Конец окна (YYYY-MM-DD), вместе с date_from"
    ),
    current_user: dict = Depends(get_current_admin),
) -> AnalyticsDashboardResponse:
    """Аналитический дашборд администратора за выбранный период."""
    resolved_from, resolved_to = _resolve_period(days, date_from, date_to)
    return await analytics_service.get_dashboard(resolved_from, resolved_to)