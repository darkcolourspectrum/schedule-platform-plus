"""
Repository для работы с Users в Schedule Service.

Источник данных: локальная таблица users_cache, которая синхронизируется
с Auth Service через consumer событий из exchange 'auth_events'.

API репозитория сохранён максимально близким к предыдущей версии (которая
читала из чужой Auth БД), чтобы минимизировать правки в потребителях.
Все методы READ-ONLY: запись в users_cache делает только consumer событий.
"""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_cache import UserCache

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository для Users (READ-ONLY из локального users_cache)."""
    
    def __init__(self, db: AsyncSession):
        # db - сессия Schedule БД (раньше была auth_db)
        self.db = db
    
    async def get_by_id(self, user_id: int) -> Optional[UserCache]:
        """Получить пользователя по ID."""
        result = await self.db.execute(
            select(UserCache).where(UserCache.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_ids(self, user_ids: List[int]) -> List[UserCache]:
        """Получить пользователей по списку ID."""
        if not user_ids:
            return []
        result = await self.db.execute(
            select(UserCache).where(UserCache.id.in_(user_ids))
        )
        return list(result.scalars().all())
    
    async def get_by_studio(self, studio_id: int) -> List[UserCache]:
        """Получить всех пользователей студии."""
        result = await self.db.execute(
            select(UserCache).where(UserCache.studio_id == studio_id)
        )
        return list(result.scalars().all())
    
    async def get_teachers_by_studio(self, studio_id: int) -> List[UserCache]:
        """Получить всех преподавателей студии."""
        result = await self.db.execute(
            select(UserCache).where(
                UserCache.studio_id == studio_id,
                UserCache.role_name == "teacher",
            )
        )
        return list(result.scalars().all())
    
    async def get_students_by_studio(self, studio_id: int) -> List[UserCache]:
        """Получить всех учеников студии."""
        result = await self.db.execute(
            select(UserCache).where(
                UserCache.studio_id == studio_id,
                UserCache.role_name == "student",
            )
        )
        return list(result.scalars().all())
    
    async def exists(self, user_id: int) -> bool:
        """Проверить существование пользователя."""
        from sqlalchemy import exists as sql_exists
        
        result = await self.db.execute(
            select(sql_exists().where(UserCache.id == user_id))
        )
        return result.scalar()
    
    def get_user_role(self, user: UserCache) -> str:
        """Получить имя роли пользователя."""
        return user.role_name or "student"
    
    def get_full_name(self, user: UserCache) -> str:
        """Получить полное имя пользователя."""
        return f"{user.first_name} {user.last_name}".strip()