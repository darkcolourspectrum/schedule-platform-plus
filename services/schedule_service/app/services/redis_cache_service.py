"""
Redis кэш сервис для Schedule Service
Предоставляет высокоуровневые методы кэширования с TTL
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json

from app.database.redis_client import redis_client
from app.config import settings

logger = logging.getLogger(__name__)


class RedisCacheService:
    """
    Сервис для кэширования данных пользователей и студий из Auth Service
    """
    
    def __init__(self):
        self.user_cache_prefix = "schedule_user"
        self.studio_cache_prefix = "schedule_studio"  
        self.permissions_cache_prefix = "schedule_permissions"
        self.teachers_cache_prefix = "schedule_teachers"
        
        # TTL настройки
        self.user_cache_ttl = 300  # 5 минут
        self.studio_cache_ttl = 600  # 10 минут
        self.permissions_cache_ttl = 300  # 5 минут
        self.teachers_cache_ttl = 900  # 15 минут
    
    def _get_user_key(self, user_id: int) -> str:
        """Ключ для кэширования пользователя"""
        return f"{self.user_cache_prefix}:{user_id}"
    
    def _get_studio_key(self, studio_id: int) -> str:
        """Ключ для кэширования студии"""
        return f"{self.studio_cache_prefix}:{studio_id}"
    
    def _get_permissions_key(self, user_id: int, studio_id: Optional[int] = None) -> str:
        """Ключ для кэширования разрешений пользователя"""
        if studio_id:
            return f"{self.permissions_cache_prefix}:{user_id}:studio_{studio_id}"
        return f"{self.permissions_cache_prefix}:{user_id}:global"
    
    def _get_teachers_key(self, studio_id: int) -> str:
        """Ключ для кэширования списка преподавателей"""
        return f"{self.teachers_cache_prefix}:studio_{studio_id}"
    
    # === Кэширование пользователей ===
    
    async def get_cached_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя из кэша"""
        try:
            key = self._get_user_key(user_id)
            data = await redis_client.get_json(key)
            
            if data:
                logger.debug(f"User cache HIT for user {user_id}")
                return data
            else:
                logger.debug(f"User cache MISS for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting cached user {user_id}: {e}")
            return None
    
    async def cache_user(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Кэширование пользователя"""
        try:
            key = self._get_user_key(user_id)
            
            # Добавляем время кэширования
            cache_data = {
                **user_data,
                "_cached_at": datetime.now().isoformat(),
                "_cache_ttl": self.user_cache_ttl
            }
            
            success = await redis_client.set(key, cache_data, expire=self.user_cache_ttl)
            
            if success:
                logger.debug(f"User {user_id} cached for {self.user_cache_ttl} seconds")
            
            return success
            
        except Exception as e:
            logger.error(f"Error caching user {user_id}: {e}")
            return False
    
    async def invalidate_user_cache(self, user_id: int) -> bool:
        """Инвалидация кэша пользователя"""
        try:
            key = self._get_user_key(user_id)
            result = await redis_client.delete(key)
            
            if result:
                logger.info(f"User {user_id} cache invalidated")
            
            return result
            
        except Exception as e:
            logger.error(f"Error invalidating user {user_id} cache: {e}")
            return False
    
    # === Кэширование студий ===
    
    async def get_cached_studio(self, studio_id: int) -> Optional[Dict[str, Any]]:
        """Получение студии из кэша"""
        try:
            key = self._get_studio_key(studio_id)
            data = await redis_client.get_json(key)
            
            if data:
                logger.debug(f"Studio cache HIT for studio {studio_id}")
                return data
            else:
                logger.debug(f"Studio cache MISS for studio {studio_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting cached studio {studio_id}: {e}")
            return None
    
    async def cache_studio(self, studio_id: int, studio_data: Dict[str, Any]) -> bool:
        """Кэширование студии"""
        try:
            key = self._get_studio_key(studio_id)
            
            cache_data = {
                **studio_data,
                "_cached_at": datetime.now().isoformat(),
                "_cache_ttl": self.studio_cache_ttl
            }
            
            success = await redis_client.set(key, cache_data, expire=self.studio_cache_ttl)
            
            if success:
                logger.debug(f"Studio {studio_id} cached for {self.studio_cache_ttl} seconds")
            
            return success
            
        except Exception as e:
            logger.error(f"Error caching studio {studio_id}: {e}")
            return False
    
    # === Кэширование разрешений ===
    
    async def get_cached_permissions(
        self, 
        user_id: int, 
        studio_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Получение разрешений пользователя из кэша"""
        try:
            key = self._get_permissions_key(user_id, studio_id)
            data = await redis_client.get_json(key)
            
            if data:
                logger.debug(f"Permissions cache HIT for user {user_id}")
                return data
            else:
                logger.debug(f"Permissions cache MISS for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting cached permissions for user {user_id}: {e}")
            return None
    
    async def cache_permissions(
        self, 
        user_id: int, 
        permissions_data: Dict[str, Any],
        studio_id: Optional[int] = None
    ) -> bool:
        """Кэширование разрешений пользователя"""
        try:
            key = self._get_permissions_key(user_id, studio_id)
            
            cache_data = {
                **permissions_data,
                "_cached_at": datetime.now().isoformat(),
                "_cache_ttl": self.permissions_cache_ttl
            }
            
            success = await redis_client.set(key, cache_data, expire=self.permissions_cache_ttl)
            
            if success:
                logger.debug(f"Permissions for user {user_id} cached")
            
            return success
            
        except Exception as e:
            logger.error(f"Error caching permissions for user {user_id}: {e}")
            return False
    
    # === Кэширование списков преподавателей ===
    
    async def get_cached_teachers(self, studio_id: int) -> Optional[List[Dict[str, Any]]]:
        """Получение списка преподавателей из кэша"""
        try:
            key = self._get_teachers_key(studio_id)
            data = await redis_client.get_json(key)
            
            if data:
                logger.debug(f"Teachers cache HIT for studio {studio_id}")
                return data.get("teachers", [])
            else:
                logger.debug(f"Teachers cache MISS for studio {studio_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting cached teachers for studio {studio_id}: {e}")
            return None
    
    async def cache_teachers(self, studio_id: int, teachers_data: List[Dict[str, Any]]) -> bool:
        """Кэширование списка преподавателей"""
        try:
            key = self._get_teachers_key(studio_id)
            
            cache_data = {
                "teachers": teachers_data,
                "_cached_at": datetime.now().isoformat(),
                "_cache_ttl": self.teachers_cache_ttl
            }
            
            success = await redis_client.set(key, cache_data, expire=self.teachers_cache_ttl)
            
            if success:
                logger.debug(f"Teachers for studio {studio_id} cached")
            
            return success
            
        except Exception as e:
            logger.error(f"Error caching teachers for studio {studio_id}: {e}")
            return False
    
    # === Инвалидация кэша ===
    
    async def invalidate_studio_cache(self, studio_id: int) -> bool:
        """Инвалидация всего кэша студии"""
        try:
            patterns = [
                f"{self.studio_cache_prefix}:{studio_id}",
                f"{self.teachers_cache_prefix}:studio_{studio_id}",
                f"{self.permissions_cache_prefix}:*:studio_{studio_id}"
            ]
            
            total_deleted = 0
            for pattern in patterns:
                if ":" in pattern and "*" not in pattern:
                    # Прямое удаление ключа
                    if await redis_client.delete(pattern):
                        total_deleted += 1
                else:
                    # Удаление по шаблону
                    total_deleted += await redis_client.clear_pattern(pattern)
            
            if total_deleted > 0:
                logger.info(f"Invalidated {total_deleted} cache entries for studio {studio_id}")
            
            return total_deleted > 0
            
        except Exception as e:
            logger.error(f"Error invalidating studio {studio_id} cache: {e}")
            return False
    
    async def invalidate_user_all_cache(self, user_id: int) -> bool:
        """Инвалидация всего кэша пользователя"""
        try:
            patterns = [
                f"{self.user_cache_prefix}:{user_id}",
                f"{self.permissions_cache_prefix}:{user_id}:*"
            ]
            
            total_deleted = 0
            for pattern in patterns:
                if "*" not in pattern:
                    if await redis_client.delete(pattern):
                        total_deleted += 1
                else:
                    total_deleted += await redis_client.clear_pattern(pattern)
            
            if total_deleted > 0:
                logger.info(f"Invalidated {total_deleted} cache entries for user {user_id}")
            
            return total_deleted > 0
            
        except Exception as e:
            logger.error(f"Error invalidating user {user_id} cache: {e}")
            return False
    
    # === Статистика кэша ===
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        try:
            stats = {}
            
            prefixes = [
                self.user_cache_prefix,
                self.studio_cache_prefix,
                self.permissions_cache_prefix,
                self.teachers_cache_prefix
            ]
            
            for prefix in prefixes:
                pattern = f"{prefix}:*"
                keys = await redis_client.get_keys_pattern(pattern)
                stats[prefix] = len(keys)
            
            return {
                "cache_statistics": stats,
                "total_cached_items": sum(stats.values()),
                "ttl_settings": {
                    "user_ttl": self.user_cache_ttl,
                    "studio_ttl": self.studio_cache_ttl,
                    "permissions_ttl": self.permissions_cache_ttl,
                    "teachers_ttl": self.teachers_cache_ttl
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}


# Глобальный экземпляр
redis_cache_service = RedisCacheService()