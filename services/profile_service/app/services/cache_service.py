"""
Сервис для работы с кэшированием данных
"""

import logging
from typing import Any, Optional, Dict, List
from app.database.redis_client import redis_client
from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Сервис для централизованного управления кэшем"""
    
    def __init__(self):
        self.redis = redis_client
        self.default_ttl = 300  # 5 минут по умолчанию
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ кэша
            
        Returns:
            Значение из кэша или None
        """
        try:
            if not self.redis.is_connected:
                return None
            
            value = await self.redis.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
            else:
                logger.debug(f"Cache MISS: {key}")
            
            return value
            
        except Exception as e:
            logger.error(f"Ошибка получения из кэша {key}: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """
        Сохранение значения в кэш
        
        Args:
            key: Ключ кэша
            value: Значение для сохранения
            ttl: Время жизни в секундах
            
        Returns:
            True если успешно сохранено
        """
        try:
            if not self.redis.is_connected:
                return False
            
            cache_ttl = ttl or self.default_ttl
            success = await self.redis.set(key, value, cache_ttl)
            
            if success:
                logger.debug(f"Cache SET: {key} (TTL: {cache_ttl}s)")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в кэш {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Удаление ключа из кэша
        
        Args:
            key: Ключ для удаления
            
        Returns:
            True если ключ был удален
        """
        try:
            if not self.redis.is_connected:
                return False
            
            success = await self.redis.delete(key)
            
            if success:
                logger.debug(f"Cache DELETE: {key}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка удаления из кэша {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """
        Удаление всех ключей по шаблону
        
        Args:
            pattern: Шаблон ключей (например: "user:123:*")
            
        Returns:
            Количество удаленных ключей
        """
        try:
            if not self.redis.is_connected:
                return 0
            
            deleted_count = await self.redis.clear_pattern(pattern)
            
            if deleted_count > 0:
                logger.debug(f"Cache CLEAR PATTERN: {pattern} ({deleted_count} keys)")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Ошибка очистки по шаблону {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """
        Проверка существования ключа в кэше
        
        Args:
            key: Ключ для проверки
            
        Returns:
            True если ключ существует
        """
        try:
            if not self.redis.is_connected:
                return False
            
            return await self.redis.exists(key)
            
        except Exception as e:
            logger.error(f"Ошибка проверки существования ключа {key}: {e}")
            return False
    
    # Специализированные методы для Profile Service
    
    async def cache_user_profile(
        self, 
        user_id: int, 
        profile_data: Dict[str, Any]
    ) -> bool:
        """Кэширование профиля пользователя"""
        key = f"profile_full:{user_id}"
        return await self.set(key, profile_data, settings.cache_user_profile_ttl)
    
    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение профиля пользователя из кэша"""
        key = f"profile_full:{user_id}"
        return await self.get(key)
    
    async def cache_dashboard(
        self, 
        user_id: int, 
        role: str, 
        dashboard_data: Dict[str, Any]
    ) -> bool:
        """Кэширование данных дашборда"""
        key = f"dashboard:{role}:{user_id}"
        return await self.set(key, dashboard_data, settings.cache_dashboard_ttl)
    
    async def get_dashboard(
        self, 
        user_id: int, 
        role: str
    ) -> Optional[Dict[str, Any]]:
        """Получение данных дашборда из кэша"""
        key = f"dashboard:{role}:{user_id}"
        return await self.get(key)
    
    async def cache_comments(
        self, 
        target_type: str, 
        target_id: int, 
        comments_data: List[Dict[str, Any]]
    ) -> bool:
        """Кэширование комментариев"""
        key = f"comments:{target_type}:{target_id}"
        return await self.set(key, comments_data, settings.cache_comments_ttl)
    
    async def get_comments(
        self, 
        target_type: str, 
        target_id: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Получение комментариев из кэша"""
        key = f"comments:{target_type}:{target_id}"
        return await self.get(key)
    
    async def cache_user_activities(
        self, 
        user_id: int, 
        activities_data: List[Dict[str, Any]]
    ) -> bool:
        """Кэширование активности пользователя"""
        key = f"activities:{user_id}"
        return await self.set(key, activities_data, settings.cache_activity_ttl)
    
    async def get_user_activities(self, user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Получение активности пользователя из кэша"""
        key = f"activities:{user_id}"
        return await self.get(key)
    
    async def invalidate_user_cache(self, user_id: int) -> int:
        """Полная очистка кэша пользователя"""
        patterns = [
            f"profile_full:{user_id}",
            f"dashboard:*:{user_id}",
            f"activities:{user_id}",
            f"comments:*:{user_id}*"
        ]
        
        total_deleted = 0
        for pattern in patterns:
            if "*" in pattern:
                deleted = await self.clear_pattern(pattern)
            else:
                deleted = 1 if await self.delete(pattern) else 0
            total_deleted += deleted
        
        logger.info(f"Очищен кэш пользователя {user_id}: {total_deleted} ключей")
        return total_deleted
    
    async def cache_teacher_stats(
        self, 
        teacher_id: int, 
        stats_data: Dict[str, Any]
    ) -> bool:
        """Кэширование статистики преподавателя"""
        key = f"teacher_stats:{teacher_id}"
        return await self.set(key, stats_data, settings.cache_dashboard_ttl)
    
    async def get_teacher_stats(self, teacher_id: int) -> Optional[Dict[str, Any]]:
        """Получение статистики преподавателя из кэша"""
        key = f"teacher_stats:{teacher_id}"
        return await self.get(key)
    
    async def cache_teacher_reviews(
        self, 
        teacher_id: int, 
        reviews_data: List[Dict[str, Any]]
    ) -> bool:
        """Кэширование отзывов о преподавателе"""
        key = f"teacher_reviews:{teacher_id}"
        return await self.set(key, reviews_data, settings.cache_comments_ttl)
    
    async def get_teacher_reviews(self, teacher_id: int) -> Optional[List[Dict[str, Any]]]:
        """Получение отзывов о преподавателе из кэша"""
        key = f"teacher_reviews:{teacher_id}"
        return await self.get(key)
    
    # Utility методы
    
    async def warm_up_cache(self, user_id: int, role: str):
        """
        Предварительный прогрев кэша для пользователя
        
        Args:
            user_id: ID пользователя
            role: Роль пользователя
        """
        try:
            logger.info(f"Начинается прогрев кэша для пользователя {user_id} ({role})")
            
            # Здесь можно добавить логику предварительной загрузки
            # наиболее часто используемых данных
            
            # Например, для преподавателей можно загрузить:
            # - Статистику
            # - Недавние отзывы
            # - Расписание на неделю
            
            if role == "teacher":
                # Прогреваем кэш преподавателя
                pass
            elif role == "student":
                # Прогреваем кэш студента
                pass
            
            logger.debug(f"Прогрев кэша завершен для пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка прогрева кэша для пользователя {user_id}: {e}")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Получение статистики использования кэша
        
        Returns:
            Словарь со статистикой кэша
        """
        try:
            if not self.redis.is_connected:
                return {"status": "disconnected", "keys_count": 0}
            
            # Здесь можно добавить реальную статистику Redis
            # Пока возвращаем базовую информацию
            
            return {
                "status": "connected",
                "redis_url": settings.redis_url,
                "default_ttl": self.default_ttl,
                "profile_ttl": settings.cache_user_profile_ttl,
                "dashboard_ttl": settings.cache_dashboard_ttl,
                "comments_ttl": settings.cache_comments_ttl,
                "activity_ttl": settings.cache_activity_ttl
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики кэша: {e}")
            return {"status": "error", "error": str(e)}


# Глобальный экземпляр сервиса кэширования
cache_service = CacheService()