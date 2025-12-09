"""Admin Dashboard Service"""
from typing import Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal, AuthAsyncSessionLocal
from app.models.studio import Studio
from app.models.classroom import Classroom
from app.models.auth_models import User
from app.schemas.dashboard import SystemStatsResponse, AdminDashboardResponse


class DashboardService:
    """Сервис для админского дашборда"""
    
    async def get_system_statistics(self) -> SystemStatsResponse:
        """Получить системную статистику"""
        # Пользователи из Auth DB
        async with AuthAsyncSessionLocal() as auth_session:
            total_users = await auth_session.scalar(select(func.count(User.id)))
            active_users = await auth_session.scalar(
                select(func.count(User.id)).where(User.is_active == True)
            )
            students = await auth_session.scalar(
                select(func.count(User.id)).where(User.role_id == 3)
            )
            teachers = await auth_session.scalar(
                select(func.count(User.id)).where(User.role_id == 2)
            )
        
        # Студии и кабинеты из Admin DB
        async with AdminAsyncSessionLocal() as admin_session:
            total_studios = await admin_session.scalar(select(func.count(Studio.id)))
            active_studios = await admin_session.scalar(
                select(func.count(Studio.id)).where(Studio.is_active == True)
            )
            total_classrooms = await admin_session.scalar(select(func.count(Classroom.id)))
            active_classrooms = await admin_session.scalar(
                select(func.count(Classroom.id)).where(Classroom.is_active == True)
            )
        
        return SystemStatsResponse(
            users={
                "total": total_users or 0,
                "active": active_users or 0,
                "students": students or 0,
                "teachers": teachers or 0
            },
            studios={
                "total": total_studios or 0,
                "active": active_studios or 0
            },
            classrooms={
                "total": total_classrooms or 0,
                "active": active_classrooms or 0
            }
        )
    
    async def get_admin_dashboard(self, admin_id: int) -> AdminDashboardResponse:
        """Получить полный дашборд админа"""
        stats = await self.get_system_statistics()
        
        return AdminDashboardResponse(
            user_id=admin_id,
            system_stats=stats,
            quick_actions=[
                {"id": "manage_users", "title": "Управление пользователями", "url": "/admin/users"},
                {"id": "manage_studios", "title": "Управление студиями", "url": "/admin/studios"},
                {"id": "system_stats", "title": "Статистика системы", "url": "/admin/stats"}
            ]
        )
