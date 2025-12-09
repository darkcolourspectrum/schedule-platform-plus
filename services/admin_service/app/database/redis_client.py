"""
Redis client for caching in Admin Service
"""

import logging
import redis.asyncio as redis
from typing import Optional, Any
import json

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Асинхронный Redis клиент для кэширования
    
    Используется для кэширования:
    - User данных из Auth Service
    - Studio данных
    - Classroom данных
    - Dashboard статистики
    """
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._connected = False
    
    async def connect(self):
        """Подключение к Redis"""
        if self._connected:
            return
        
        try:
            self.redis = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5
            )
            
            # Проверяем подключение
            await self.redis.ping()
            self._connected = True
            logger.info(f"✅ Redis connected: {settings.redis_url}")
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.redis = None
            self._connected = False
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis disconnected")
    
    async def get(self, key: str) -> Optional[str]:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ кэша
            
        Returns:
            Значение или None если не найдено
        """
        if not self.redis:
            return None
        
        try:
            value = await self.redis.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
            else:
                logger.debug(f"Cache MISS: {key}")
            return value
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Установка значения в кэш
        
        Args:
            key: Ключ кэша
            value: Значение
            ttl: Time to live в секундах
            
        Returns:
            True если успешно, False если ошибка
        """
        if not self.redis:
            return False
        
        try:
            if ttl:
                await self.redis.setex(key, ttl, value)
            else:
                await self.redis.set(key, value)
            
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    async def setex(self, key: str, ttl: int, value: str) -> bool:
        """
        Установка значения с TTL
        
        Args:
            key: Ключ кэша
            ttl: Time to live в секундах
            value: Значение
            
        Returns:
            True если успешно
        """
        return await self.set(key, value, ttl)
    
    async def delete(self, key: str) -> bool:
        """
        Удаление ключа из кэша
        
        Args:
            key: Ключ кэша
            
        Returns:
            True если удалён
        """
        if not self.redis:
            return False
        
        try:
            deleted = await self.redis.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return deleted > 0
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Проверка существования ключа
        
        Args:
            key: Ключ кэша
            
        Returns:
            True если существует
        """
        if not self.redis:
            return False
        
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """
        Установка TTL для существующего ключа
        
        Args:
            key: Ключ кэша
            ttl: Time to live в секундах
            
        Returns:
            True если успешно
        """
        if not self.redis:
            return False
        
        try:
            return await self.redis.expire(key, ttl)
        except Exception as e:
            logger.error(f"Redis EXPIRE error for key {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """
        Удаление всех ключей по паттерну
        
        Args:
            pattern: Паттерн ключей (например: "user:*")
            
        Returns:
            Количество удалённых ключей
        """
        if not self.redis:
            return 0
        
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"Cleared {deleted} keys matching pattern: {pattern}")
                return deleted
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR_PATTERN error for pattern {pattern}: {e}")
            return 0
    
    async def get_json(self, key: str) -> Optional[Any]:
        """Получение JSON из кэша"""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON for key: {key}")
                return None
        return None
    
    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Установка JSON в кэш"""
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ttl)
        except Exception as e:
            logger.error(f"Failed to encode JSON for key {key}: {e}")
            return False
    
    @property
    def is_connected(self) -> bool:
        """Проверка подключения к Redis"""
        return self._connected


# Глобальный экземпляр Redis клиента
redis_client = RedisClient()
