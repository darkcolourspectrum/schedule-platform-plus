from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models.role import Role, RoleType


class RoleRepository(BaseRepository[Role]):
    """Репозиторий для работы с ролями"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Role, db)
    
    async def get_by_name(self, name: str) -> Optional[Role]:
        """Получение роли по названию"""
        return await self.get_by_field("name", name)
    
    async def get_default_student_role(self) -> Optional[Role]:
        """Получение роли студента по умолчанию"""
        return await self.get_by_name(RoleType.STUDENT.value)
    
    async def get_teacher_role(self) -> Optional[Role]:
        """Получение роли преподавателя"""
        return await self.get_by_name(RoleType.TEACHER.value)
    
    async def get_admin_role(self) -> Optional[Role]:
        """Получение роли администратора"""
        return await self.get_by_name(RoleType.ADMIN.value)
    
    async def create_default_roles(self) -> None:
        """Создание ролей по умолчанию"""
        default_roles = [
            {
                "name": RoleType.ADMIN.value,
                "description": "Администратор с полными правами доступа"
            },
            {
                "name": RoleType.TEACHER.value,
                "description": "Преподаватель с правами управления расписанием"
            },
            {
                "name": RoleType.STUDENT.value,
                "description": "Ученик с базовыми правами"
            },
            {
                "name": RoleType.GUEST.value,
                "description": "Гость для пробных уроков"
            }
        ]
        
        for role_data in default_roles:
            # Проверяем, существует ли роль
            existing_role = await self.get_by_name(role_data["name"])
            if not existing_role:
                await self.create(**role_data)