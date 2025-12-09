"""Admin Dashboard API endpoints"""
from fastapi import APIRouter, Depends

from app.core.auth import get_current_admin
from app.services.dashboard_service import DashboardService
from app.schemas.dashboard import SystemStatsResponse, AdminDashboardResponse
from app.dependencies import get_dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Admin Dashboard"])


@router.get("/system-stats", response_model=SystemStatsResponse)
async def get_system_stats(
    current_user: dict = Depends(get_current_admin),
    service: DashboardService = Depends(get_dashboard_service)
):
    """Получить системную статистику"""
    return await service.get_system_statistics()


@router.get("", response_model=AdminDashboardResponse)
async def get_admin_dashboard(
    current_user: dict = Depends(get_current_admin),
    service: DashboardService = Depends(get_dashboard_service)
):
    """Получить полный дашборд администратора"""
    return await service.get_admin_dashboard(current_user["id"])
