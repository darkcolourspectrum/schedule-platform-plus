"""
Сервис для работы с кэшированием через Redis
"""

import json
import logging
from typing import Any, Optional, Dict, List
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Сервис для работы с Redis кэшем"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.enabled = True
        self._connected = False
    
    async def _connect(self):
        """Внутреннее подключение к Redis"""
        if self._connected:
            return
        
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Проверяем подключение
            await self.redis_client.ping()
            self._connected = True
            self.enabled = True
            logger.info("✅ Redis подключен успешно")
            
        except Exception as e:
            logger.warning(f"⚠️ Redis недоступен: {e}")
            self.enabled = False
            self._connected = False
            self.redis_client = None
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self._connected = False
            logger.info("Redis соединение закрыто")
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Сохранение значения в кэш
        
        Args:
            key: Ключ
            value: Значение для сохранения
            ttl: Время жизни в секундах
            
        Returns:
            True если успешно сохранено
        """
        if not self.enabled:
            return False
        
        try:
            await self._connect()
            if not self._connected:
                return False
            
            json_value = json.dumps(value, default=str)
            
            if ttl:
                result = await self.redis_client.setex(key, ttl, json_value)
            else:
                result = await self.redis_client.set(key, json_value)
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в кэш {key}: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ
            
        Returns:
            Значение или None
        """
        if not self.enabled:
            return None
        
        try:
            await self._connect()
            if not self._connected:
                return None
            
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения из кэша {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """
        Удаление ключа из кэша
        
        Args:
            key: Ключ для удаления
            
        Returns:
            True если успешно удалено
        """
        if not self.enabled:
            return False
        
        try:
            await self._connect()
            if not self._connected:
                return False
            
            result = await self.redis_client.delete(key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Ошибка удаления из кэша {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        if not self.enabled:
            return False
        
        try:
            await self._connect()
            if not self._connected:
                return False
            
            result = await self.redis_client.exists(key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Ошибка проверки существования ключа {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """
        Удаление ключей по паттерну
        
        Args:
            pattern: Паттерн для поиска ключей
            
        Returns:
            Количество удаленных ключей
        """
        if not self.enabled:
            return 0
        
        try:
            await self._connect()
            if not self._connected:
                return 0
            
            keys = await self.redis_client.keys(pattern)
            if keys:
                result = await self.redis_client.delete(*keys)
                logger.debug(f"Удалено {result} ключей по паттерну {pattern}")
                return result
            return 0
            
        except Exception as e:
            logger.error(f"Ошибка удаления по паттерну {pattern}: {e}")
            return 0
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Увеличение числового значения"""
        if not self.enabled:
            return None
        
        try:
            await self._connect()
            if not self._connected:
                return None
            
            result = await self.redis_client.incrby(key, amount)
            return result
            
        except Exception as e:
            logger.error(f"Ошибка инкремента ключа {key}: {e}")
            return None
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Получение статистики Redis
        
        Returns:
            Словарь со статистикой кэша
        """
        try:
            await self._connect()
            
            if not self._connected:
                return {
                    "status": "disconnected",
                    "enabled": False,
                    "redis_url": settings.redis_url,
                    "error": "Unable to connect to Redis"
                }
            
            # Получаем информацию о Redis
            info = await self.redis_client.info()
            
            return {
                "status": "connected",
                "enabled": True,
                "redis_url": settings.redis_url,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "redis_version": info.get("redis_version", "unknown")
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики Redis: {e}")
            return {
                "status": "error",
                "enabled": False,
                "error": str(e)
            }
    
    # Методы для специфичного кэширования Profile Service
    
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


# Глобальный экземпляр сервиса кэширования
cache_service = CacheService()