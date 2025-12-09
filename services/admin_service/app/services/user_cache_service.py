"""
User Cache Service - Кэширование User данных из Auth Service

ВАЖНО: Это КЛЮЧЕВОЙ сервис для убирания HTTP вызовов между сервисами!

Вместо HTTP запросов в Auth Service, мы:
1. Проверяем Redis кэш
2. Если нет в кэше - читаем напрямую из Auth Service БД (READ-ONLY)
3. Кэшируем результат в Redis

Преимущества:
- Нет HTTP overhead
- Данные всегда актуальные
- Быстро (Redis)
- Надёжно (нет зависимости от доступности HTTP API)
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.auth_models import User, Role
from app.database.connection import AuthAsyncSessionLocal
from app.database.redis_client import redis_client
from app.config import settings

logger = logging.getLogger(__name__)


class UserCacheService:
    """
    Сервис для получения User данных с кэшированием
    
    Workflow:
    1. Проверяем Redis: user:{id}
    2. Если нет → читаем из Auth Service БД
    3. Кэшируем на 5 минут
    4. Возвращаем данные
    """
    
    def __init__(self):
        self.cache_ttl = settings.cache_user_ttl
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить пользователя по ID с кэшированием
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Словарь с данными пользователя или None
        """
        # 1. Проверяем Redis кэш
        cache_key = f"user:{user_id}"
        cached = await redis_client.get_json(cache_key)
        
        if cached:
            logger.debug(f"User {user_id} loaded from cache")
            return cached
        
        # 2. Читаем из Auth Service БД
        logger.debug(f"User {user_id} not in cache, loading from Auth DB")
        user_data = await self._get_user_from_auth_db(user_id)
        
        if not user_data:
            logger.warning(f"User {user_id} not found in Auth DB")
            return None
        
        # 3. Кэшируем результат
        await redis_client.set_json(cache_key, user_data, self.cache_ttl)
        logger.debug(f"User {user_id} cached for {self.cache_ttl}s")
        
        return user_data
    
    async def get_users_by_role(
        self,
        role_name: str,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить всех пользователей с определённой ролью
        
        Args:
            role_name: Название роли (admin, teacher, student, guest)
            is_active: Фильтр по активности (опционально)
            
        Returns:
            Список пользователей
        """
        # Кэшируем список пользователей по роли
        cache_key = f"users:role:{role_name}:active:{is_active}"
        cached = await redis_client.get_json(cache_key)
        
        if cached:
            logger.debug(f"Users with role {role_name} loaded from cache")
            return cached
        
        # Читаем из БД
        logger.debug(f"Loading users with role {role_name} from Auth DB")
        users_data = await self._get_users_by_role_from_db(role_name, is_active)
        
        # Кэшируем на 2 минуты (короче, т.к. список может меняться)
        await redis_client.set_json(cache_key, users_data, 120)
        
        return users_data
    
    async def get_users_by_studio(
        self,
        studio_id: int,
        role_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить всех пользователей студии
        
        Args:
            studio_id: ID студии
            role_name: Фильтр по роли (опционально)
            
        Returns:
            Список пользователей
        """
        cache_key = f"users:studio:{studio_id}:role:{role_name}"
        cached = await redis_client.get_json(cache_key)
        
        if cached:
            return cached
        
        users_data = await self._get_users_by_studio_from_db(studio_id, role_name)
        await redis_client.set_json(cache_key, users_data, 120)
        
        return users_data
    
    async def invalidate_user_cache(self, user_id: int):
        """
        Инвалидация кэша пользователя
        
        Вызывается когда User обновился в Auth Service
        """
        cache_key = f"user:{user_id}"
        deleted = await redis_client.delete(cache_key)
        
        if deleted:
            logger.info(f"User {user_id} cache invalidated")
        
        # Также инвалидируем списки пользователей
        await redis_client.clear_pattern("users:*")
    
    async def invalidate_all_users_cache(self):
        """Инвалидация кэша всех пользователей"""
        deleted = await redis_client.clear_pattern("user:*")
        await redis_client.clear_pattern("users:*")
        logger.info(f"All users cache invalidated ({deleted} keys)")
    
    # ========== ПРИВАТНЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С БД ==========
    
    async def _get_user_from_auth_db(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Читаем пользователя из Auth Service БД (READ-ONLY)
        
        ВАЖНО: Только чтение! Не модифицируем!
        """
        async with AuthAsyncSessionLocal() as session:
            try:
                stmt = (
                    select(User)
                    .where(User.id == user_id)
                    .options(selectinload(User.role))
                )
                
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                return self._user_to_dict(user)
                
            except Exception as e:
                logger.error(f"Error reading user {user_id} from Auth DB: {e}")
                return None
    
    async def _get_users_by_role_from_db(
        self,
        role_name: str,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Читаем пользователей по роли из Auth Service БД"""
        async with AuthAsyncSessionLocal() as session:
            try:
                stmt = (
                    select(User)
                    .join(User.role)
                    .where(Role.name == role_name)
                    .options(selectinload(User.role))
                )
                
                # Фильтр по активности
                if is_active is not None:
                    stmt = stmt.where(User.is_active == is_active)
                
                result = await session.execute(stmt)
                users = result.scalars().all()
                
                return [self._user_to_dict(user) for user in users]
                
            except Exception as e:
                logger.error(f"Error reading users with role {role_name} from Auth DB: {e}")
                return []
    
    async def _get_users_by_studio_from_db(
        self,
        studio_id: int,
        role_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Читаем пользователей студии из Auth Service БД"""
        async with AuthAsyncSessionLocal() as session:
            try:
                stmt = (
                    select(User)
                    .where(User.studio_id == studio_id)
                    .options(selectinload(User.role))
                )
                
                # Фильтр по роли
                if role_name:
                    stmt = stmt.join(User.role).where(Role.name == role_name)
                
                result = await session.execute(stmt)
                users = result.scalars().all()
                
                return [self._user_to_dict(user) for user in users]
                
            except Exception as e:
                logger.error(f"Error reading users for studio {studio_id} from Auth DB: {e}")
                return []
    
    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        """
        Конвертируем User SQLAlchemy объект в словарь
        
        ВАЖНО: Это единственное место где мы формируем структуру User данных
        """
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "role": {
                "id": user.role.id,
                "name": user.role.name,
                "description": user.role.description
            } if user.role else None,
            "studio_id": user.studio_id,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_locked": user.is_locked,
            "login_attempts": user.login_attempts,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "privacy_policy_accepted": user.privacy_policy_accepted
        }


# Singleton instance
user_cache_service = UserCacheService()
