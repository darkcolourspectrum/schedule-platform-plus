"""
Репозиторий для работы с локальной копией пользователей (users_cache).

users_cache наполняется consumer'ом событий auth_events и используется
CRM только на чтение. Этот репозиторий инкапсулирует запросы к кешу:
проверку существования пользователя и обогащение ответов именами.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_cache import UserCache


class UserCacheRepository:
    """Доступ на чтение к локальной копии пользователей."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> Optional[UserCache]:
        """Получить пользователя из кеша по id."""
        result = await self.db.execute(
            select(UserCache).where(UserCache.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_many_by_ids(
        self, user_ids: list[int]
    ) -> dict[int, UserCache]:
        """
        Получить несколько пользователей по списку id одним запросом.

        Возвращает словарь {id: UserCache} - для обогащения списка лидов
        именами ответственных без N+1 запросов.
        """
        if not user_ids:
            return {}
        result = await self.db.execute(
            select(UserCache).where(UserCache.id.in_(user_ids))
        )
        return {user.id: user for user in result.scalars().all()}