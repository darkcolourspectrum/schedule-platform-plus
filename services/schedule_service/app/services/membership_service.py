"""
Service для membership-операций над студиями.

Объединяет чтение из локальных кешей (users_cache, studios_cache,
classrooms_cache), которые синхронизируются из Auth и Admin сервисов
через события.

Этот сервис - точка входа для UI-модалок расписания (создание занятия,
шаблона), которым нужны список студий, кабинетов и пользователей
конкретной студии. Без него фронт ходил на admin-эндпоинты и упирался
в 403 для преподавателей.
"""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio_cache import StudioCache
from app.models.classroom_cache import ClassroomCache
from app.models.user_cache import UserCache
from app.repositories.studio_cache_repository import StudioCacheRepository
from app.repositories.classroom_cache_repository import ClassroomCacheRepository
from app.repositories.user_repository import UserRepository


class MembershipService:
    """Чтение студий, кабинетов и членов студий из локальных кешей."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.studio_repo = StudioCacheRepository(db)
        self.classroom_repo = ClassroomCacheRepository(db)
        self.user_repo = UserRepository(db)
    
    async def get_studios_for_user(
        self,
        user: dict,
    ) -> List[StudioCache]:
        """
        Получить список студий, доступных пользователю.
        
        Admin: все активные студии.
        Teacher/Student: только студия, к которой они привязаны.
        """
        from app.core.security import extract_role_name
        
        role = extract_role_name(user.get("role"))
        
        if role == "admin":
            return await self.studio_repo.get_all(active_only=True)
        
        user_studio_id = user.get("studio_id")
        if user_studio_id is None:
            return []
        
        return await self.studio_repo.get_by_ids(
            [user_studio_id],
            active_only=True,
        )
    
    async def get_studio_classrooms(
        self,
        studio_id: int,
    ) -> List[ClassroomCache]:
        """
        Получить активные кабинеты студии.
        
        Проверка доступа делается на уровне endpoint'а через
        check_studio_access(user, studio_id).
        """
        return await self.classroom_repo.get_by_studio(
            studio_id,
            active_only=True,
        )
    
    async def get_studio_teachers(self, studio_id: int) -> List[UserCache]:
        """Получить активных преподавателей студии."""
        teachers = await self.user_repo.get_teachers_by_studio(studio_id)
        return [t for t in teachers if t.is_active]
    
    async def get_studio_students(self, studio_id: int) -> List[UserCache]:
        """Получить активных учеников студии."""
        students = await self.user_repo.get_students_by_studio(studio_id)
        return [s for s in students if s.is_active]