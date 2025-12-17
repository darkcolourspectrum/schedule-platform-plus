"""
Repository для работы с Users (READ-ONLY из Auth Service БД)
"""

import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth_models import User, Role

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository для Users (READ-ONLY)"""
    
    def __init__(self, auth_db: AsyncSession):
        self.db = auth_db
    
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_ids(self, user_ids: List[int]) -> List[User]:
        """Получить пользователей по списку ID"""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id.in_(user_ids))
        )
        return list(result.scalars().all())
    
    async def get_by_studio(self, studio_id: int) -> List[User]:
        """Получить всех пользователей студии"""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.studio_id == studio_id)
        )
        return list(result.scalars().all())
    
    async def get_teachers_by_studio(self, studio_id: int) -> List[User]:
        """Получить всех преподавателей студии"""
        result = await self.db.execute(
            select(User)
            .join(Role)
            .options(selectinload(User.role))
            .where(
                User.studio_id == studio_id,
                Role.name == "teacher"
            )
        )
        return list(result.scalars().all())
    
    async def get_students_by_studio(self, studio_id: int) -> List[User]:
        """Получить всех учеников студии"""
        result = await self.db.execute(
            select(User)
            .join(Role)
            .options(selectinload(User.role))
            .where(
                User.studio_id == studio_id,
                Role.name == "student"
            )
        )
        return list(result.scalars().all())
    
    async def exists(self, user_id: int) -> bool:
        """Проверить существование пользователя"""
        from sqlalchemy import exists as sql_exists
        
        result = await self.db.execute(
            select(sql_exists().where(User.id == user_id))
        )
        return result.scalar()
    
    def get_user_role(self, user: User) -> str:
        """Получить имя роли пользователя"""
        if hasattr(user, 'role') and user.role:
            return user.role.name
        return "student"
    
    def get_full_name(self, user: User) -> str:
        """Получить полное имя пользователя"""
        return f"{user.first_name} {user.last_name}".strip()
