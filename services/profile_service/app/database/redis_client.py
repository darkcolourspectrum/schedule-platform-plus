"""
Redis client configuration for Profile Service
Настройка Redis клиента для кэширования данных
"""

import json
import logging
from typing import Optional, Any, Dict, Union
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Асинхронный Redis клиент для Profile Service"""
    
    def __init__(self):
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[redis.Redis] = None
        self._connected = False
    
    async def connect(self):
        """Подключение к Redis"""
        try:
            self.pool = ConnectionPool.from_url(
                settings.redis_url,
                decode_responses=True,
                encoding='utf-8',
                max_connections=20,
                retry_on_timeout=True
            )
            
            self.client = redis.Redis(connection_pool=self.pool)
            
            # Проверяем соединение
            await self.client.ping()
            self._connected = True
            
            logger.info("Redis connection established successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            raise
    
    async def disconnect(self):
        """Отключение от Redis"""
        try:
            if self.client:
                await self.client.close()
            if self.pool:
                await self.pool.disconnect()
            
            self._connected = False
            logger.info("Redis connection closed")
            
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Проверка состояния соединения"""
        return self._connected
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        serialize: bool = True
    ) -> bool:
        """
        Сохранение значения в Redis
        
        Args:
            key: Ключ
            value: Значение (будет сериализовано в JSON если serialize=True)
            ttl: Время жизни в секундах
            serialize: Сериализовать ли значение в JSON
        """
        if not self.client or not self._connected:
            logger.warning("Redis client not connected")
            return False
        
        try:
            if serialize:
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting Redis key {key}: {e}")
            return False
    
    async def get(
        self, 
        key: str, 
        deserialize: bool = True
    ) -> Optional[Any]:
        """
        Получение значения из Redis
        
        Args:
            key: Ключ
            deserialize: Десериализовать ли из JSON
        """
        if not self.client or not self._connected:
            logger.warning("Redis client not connected")
            return None
        
        try:
            value = await self.client.get(key)
            
            if value is None:
                return None
            
            if deserialize:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to deserialize value for key {key}")
                    return value
            
            return value
            
        except Exception as e:
            logger.error(f"Error getting Redis key {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Удаление ключа из Redis"""
        if not self.client or not self._connected:
            return False
        
        try:
            result = await self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Error deleting Redis key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        if not self.client or not self._connected:
            return False
        
        try:
            result = await self.client.exists(key)
            return result > 0
        except Exception as e:
            logger.error(f"Error checking Redis key {key}: {e}")
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Установка времени жизни для ключа"""
        if not self.client or not self._connected:
            return False
        
        try:
            result = await self.client.expire(key, ttl)
            return result
        except Exception as e:
            logger.error(f"Error setting TTL for Redis key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Удаление ключей по паттерну
        Осторожно: может быть медленным на больших БД
        """
        if not self.client or not self._connected:
            return 0
        
        try:
            keys = await self.client.keys(pattern)
            if keys:
                result = await self.client.delete(*keys)
                return result
            return 0
        except Exception as e:
            logger.error(f"Error deleting Redis keys by pattern {pattern}: {e}")
            return 0
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Увеличение числового значения"""
        if not self.client or not self._connected:
            return None
        
        try:
            result = await self.client.incrby(key, amount)
            return result
        except Exception as e:
            logger.error(f"Error incrementing Redis key {key}: {e}")
            return None
    
    async def hash_set(
        self, 
        key: str, 
        field: str, 
        value: Any,
        serialize: bool = True
    ) -> bool:
        """Установка значения в Redis hash"""
        if not self.client or not self._connected:
            return False
        
        try:
            if serialize:
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            await self.client.hset(key, field, value)
            return True
        except Exception as e:
            logger.error(f"Error setting Redis hash {key}:{field}: {e}")
            return False
    
    async def hash_get(
        self, 
        key: str, 
        field: str, 
        deserialize: bool = True
    ) -> Optional[Any]:
        """Получение значения из Redis hash"""
        if not self.client or not self._connected:
            return None
        
        try:
            value = await self.client.hget(key, field)
            
            if value is None:
                return None
            
            if deserialize:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            
            return value
        except Exception as e:
            logger.error(f"Error getting Redis hash {key}:{field}: {e}")
            return None
    
    async def hash_delete(self, key: str, field: str) -> bool:
        """Удаление поля из Redis hash"""
        if not self.client or not self._connected:
            return False
        
        try:
            result = await self.client.hdel(key, field)
            return result > 0
        except Exception as e:
            logger.error(f"Error deleting Redis hash field {key}:{field}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния Redis"""
        if not self.client:
            return {"status": "disconnected", "error": "Client not initialized"}
        
        try:
            start_time = await self.client.time()
            await self.client.ping()
            info = await self.client.info()
            
            return {
                "status": "healthy",
                "connected": self._connected,
                "server_time": start_time,
                "version": info.get("redis_version"),
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients")
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Глобальный экземпляр Redis клиента
redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Dependency для получения Redis клиента"""
    if not redis_client.is_connected:
        await redis_client.connect()
    return redis_client


async def init_redis():
    """Инициализация Redis соединения"""
    await redis_client.connect()


async def close_redis():
    """Закрытие Redis соединения"""
    await redis_client.disconnect()


if __name__ == "__main__":
    """Скрипт для проверки подключения к Redis"""
    import asyncio
    
    async def main():
        print("🔍 Проверка подключения к Redis...")
        
        try:
            await redis_client.connect()
            print("✅ Подключение к Redis успешно")
            
            # Тест записи/чтения
            test_key = "profile_service:test"
            test_data = {"message": "Hello from Profile Service", "timestamp": "2025-01-01"}
            
            print("📝 Тестирование записи данных...")
            await redis_client.set(test_key, test_data, ttl=60)
            
            print("📖 Тестирование чтения данных...")
            result = await redis_client.get(test_key)
            print(f"Результат: {result}")
            
            print("🗑️ Удаление тестовых данных...")
            await redis_client.delete(test_key)
            
            # Health check
            print("🏥 Проверка состояния Redis...")
            health = await redis_client.health_check()
            print(f"Состояние: {health}")
            
        except Exception as e:
            print(f"❌ Ошибка при работе с Redis: {e}")
        finally:
            await redis_client.disconnect()
            print("🎉 Проверка завершена")
    
    asyncio.run(main())