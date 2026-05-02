"""
User Cache Service - чтение данных пользователей из локальной таблицы users_cache.

Источник данных: локальная таблица users_cache в Admin Service БД.
Эта таблица синхронизируется с Auth Service через consumer событий 'auth_events'
(см. app/messaging/auth_consumer.py и auth_handlers.py).

Для записи (изменение роли, активация, привязка к студии) использовать
AuthServiceClient (HTTP-вызовы к Auth Service), а НЕ напрямую этот сервис.

"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal
from app.models.user_cache import UserCache

logger = logging.getLogger(__name__)


# Заглушки описаний ролей (их нет в users_cache - они хранятся в Auth Service).
# Если в будущем потребуются в админке - получать через AuthServiceClient.


class UserCacheService:
    """Сервис чтения пользователей из локальной users_cache."""
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по ID из локального кеша."""
        async with AdminAsyncSessionLocal() as session:
            user = await self._fetch_one(session, user_id)
            if user is None:
                return None
            return self._user_to_dict(user)
    
    async def get_users_by_role(
        self,
        role_name: str,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Получить пользователей с указанной ролью."""
        async with AdminAsyncSessionLocal() as session:
            stmt = select(UserCache).where(UserCache.role_name == role_name)
            if is_active is not None:
                stmt = stmt.where(UserCache.is_active == is_active)
            stmt = stmt.order_by(UserCache.id)
            
            result = await session.execute(stmt)
            users = list(result.scalars().all())
            return [self._user_to_dict(u) for u in users]
    
    async def get_users_by_studio(
        self,
        studio_id: int,
        role_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Получить всех пользователей студии."""
        async with AdminAsyncSessionLocal() as session:
            stmt = select(UserCache).where(UserCache.studio_id == studio_id)
            if role_name:
                stmt = stmt.where(UserCache.role_name == role_name)
            stmt = stmt.order_by(UserCache.id)
            
            result = await session.execute(stmt)
            users = list(result.scalars().all())
            return [self._user_to_dict(u) for u in users]
    
    async def get_all_users(
        self,
        limit: int = 50,
        offset: int = 0,
        role_name: Optional[str] = None,
        studio_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Получить пользователей с фильтрами и пагинацией."""
        async with AdminAsyncSessionLocal() as session:
            stmt = select(UserCache)
            if role_name:
                stmt = stmt.where(UserCache.role_name == role_name)
            if studio_id is not None:
                stmt = stmt.where(UserCache.studio_id == studio_id)
            if is_active is not None:
                stmt = stmt.where(UserCache.is_active == is_active)
            stmt = stmt.order_by(UserCache.id).limit(limit).offset(offset)
            
            result = await session.execute(stmt)
            users = list(result.scalars().all())
            return [self._user_to_dict(u) for u in users]
    
    async def count_users(
        self,
        role_name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        """Посчитать пользователей с фильтрами (для dashboard-статистики)."""
        from sqlalchemy import func
        
        async with AdminAsyncSessionLocal() as session:
            stmt = select(func.count(UserCache.id))
            if role_name:
                stmt = stmt.where(UserCache.role_name == role_name)
            if is_active is not None:
                stmt = stmt.where(UserCache.is_active == is_active)
            
            result = await session.execute(stmt)
            return result.scalar() or 0
    
    async def _fetch_one(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> Optional[UserCache]:
        result = await session.execute(
            select(UserCache).where(UserCache.id == user_id)
        )
        return result.scalar_one_or_none()
    
    def _user_to_dict(self, user: UserCache) -> Dict[str, Any]:
        """
        Конвертировать UserCache в словарь, совместимый с прежним API.
        
        Сохраняем структуру 'role' как вложенный объект, чтобы не ломать
        существующие Pydantic-схемы в админке.
        """
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name} {user.last_name}".strip(),
            "phone": user.phone,
            "role_id": user.role_id,
            "role": user.role_name,
            "studio_id": user.studio_id,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            # Поля, которых нет в users_cache: возвращаем None/0, чтобы не
            # ломать схемы. Эти поля используются дашбордом и user_management:
            # их нужно либо получать через AuthServiceClient, либо признать,
            # что в admin они не критичны (login_attempts, last_login и т.п.).
            "is_locked": False,
            "login_attempts": 0,
            "locked_until": None,
            "last_login": None,
            "created_at": user.synced_at.isoformat() if user.synced_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "privacy_policy_accepted": True,
            "privacy_policy_accepted_at": None,
        }


# Singleton instance
user_cache_service = UserCacheService()