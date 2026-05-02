"""
Admin Dashboard Service.

Чтение статистики пользователей идёт из локального users_cache
(через UserCacheService), а не из чужой Auth БД. Это устраняет последний
прямой доступ Admin Service к Auth БД.
"""

from sqlalchemy import select, func

from app.database.connection import AdminAsyncSessionLocal
from app.models.studio import Studio
from app.models.classroom import Classroom
from app.services.user_cache_service import user_cache_service
from app.schemas.dashboard import SystemStatsResponse, AdminDashboardResponse


class DashboardService:
    """Сервис для админского дашборда."""
    
    async def get_system_statistics(self) -> SystemStatsResponse:
        """Получить системную статистику."""
        # Пользователи - из локального users_cache
        total_users = await user_cache_service.count_users()
        active_users = await user_cache_service.count_users(is_active=True)
        students = await user_cache_service.count_users(role_name="student")
        teachers = await user_cache_service.count_users(role_name="teacher")
        
        # Студии и кабинеты - из Admin БД (как и раньше)
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
                "total": total_users,
                "active": active_users,
                "students": students,
                "teachers": teachers,
            },
            studios={
                "total": total_studios or 0,
                "active": active_studios or 0,
            },
            classrooms={
                "total": total_classrooms or 0,
                "active": active_classrooms or 0,
            },
        )
    
    async def get_admin_dashboard(self, admin_id: int) -> AdminDashboardResponse:
        """Получить полный дашборд админа."""
        stats = await self.get_system_statistics()
        
        return AdminDashboardResponse(
            user_id=admin_id,
            system_stats=stats,
            quick_actions=[
                {"id": "manage_users", "title": "Управление пользователями", "url": "/admin/users"},
                {"id": "manage_studios", "title": "Управление студиями", "url": "/admin/studios"},
                {"id": "system_stats", "title": "Статистика системы", "url": "/admin/stats"},
            ],
        )