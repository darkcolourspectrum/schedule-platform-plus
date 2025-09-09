"""
Redis клиент для Profile Service
Используется для кэширования данных профилей, дашбордов и активности
"""

import asyncio
import json
import logging
from typing import Any, Optional, Union
import redis.asyncio as redis
from redis.asyncio import Redis
import sys

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Асинхронный Redis клиент для Profile Service"""
    
    def __init__(self):
        self._redis: Optional[Redis] = None
        self._connected = False
    
    async def connect(self) -> None:
        """Подключение к Redis"""
        try:
            self._redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # Проверяем подключение
            await self._redis.ping()
            self._connected = True
            logger.info(f"✅ Подключение к Redis установлено: {settings.redis_url}")
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось подключиться к Redis: {e}")
            self._connected = False
            self._redis = None
    
    async def disconnect(self) -> None:
        """Отключение от Redis"""
        if self._redis:
            try:
                await self._redis.close()
                logger.info("🔐 Соединение с Redis закрыто")
            except Exception as e:
                logger.error(f"Ошибка при закрытии Redis соединения: {e}")
            finally:
                self._redis = None
                self._connected = False
    
    async def test_connection(self) -> bool:
        """Проверка подключения к Redis"""
        if not self._redis:
            return False
        
        try:
            await self._redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            return False
    
    @property
    def is_connected(self) -> bool:
        """Проверка статуса подключения"""
        return self._connected and self._redis is not None
    
    # === Основные операции с кэшем ===
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """
        Установка значения в кэш
        
        Args:
            key: Ключ
            value: Значение (будет сериализовано в JSON)
            ttl: Время жизни в секундах
        
        Returns:
            bool: True если успешно
        """
        if not self.is_connected:
            logger.warning("Redis не подключен, кэширование пропущено")
            return False
        
        try:
            # Сериализуем значение в JSON
            serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            
            if ttl:
                await self._redis.setex(key, ttl, serialized_value)
            else:
                await self._redis.set(key, serialized_value)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка записи в Redis {key}: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ
        
        Returns:
            Any: Десериализованное значение или None
        """
        if not self.is_connected:
            return None
        
        try:
            value = await self._redis.get(key)
            if value is None:
                return None
            
            # Десериализуем из JSON
            return json.loads(value)
            
        except Exception as e:
            logger.error(f"Ошибка чтения из Redis {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """
        Удаление ключа из кэша
        
        Args:
            key: Ключ для удаления
        
        Returns:
            bool: True если ключ был удален
        """
        if not self.is_connected:
            return False
        
        try:
            result = await self._redis.delete(key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Ошибка удаления из Redis {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Проверка существования ключа
        
        Args:
            key: Ключ для проверки
        
        Returns:
            bool: True если ключ существует
        """
        if not self.is_connected:
            return False
        
        try:
            result = await self._redis.exists(key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Ошибка проверки существования ключа {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """
        Удаление всех ключей по шаблону
        
        Args:
            pattern: Шаблон ключей (например: "user:123:*")
        
        Returns:
            int: Количество удаленных ключей
        """
        if not self.is_connected:
            return 0
        
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                deleted = await self._redis.delete(*keys)
                logger.info(f"Удалено ключей по шаблону '{pattern}': {deleted}")
                return deleted
            return 0
            
        except Exception as e:
            logger.error(f"Ошибка удаления ключей по шаблону {pattern}: {e}")
            return 0
    
    # === Специальные методы для Profile Service ===
    
    async def cache_user_profile(
        self, 
        user_id: int, 
        profile_data: dict
    ) -> bool:
        """Кэширование профиля пользователя"""
        key = f"user_profile:{user_id}"
        return await self.set(key, profile_data, settings.cache_user_profile_ttl)
    
    async def get_user_profile(self, user_id: int) -> Optional[dict]:
        """Получение профиля пользователя из кэша"""
        key = f"user_profile:{user_id}"
        return await self.get(key)
    
    async def cache_dashboard(
        self, 
        user_id: int, 
        role: str, 
        dashboard_data: dict
    ) -> bool:
        """Кэширование данных дашборда"""
        key = f"dashboard:{role}:{user_id}"
        return await self.set(key, dashboard_data, settings.cache_dashboard_ttl)
    
    async def get_dashboard(self, user_id: int, role: str) -> Optional[dict]:
        """Получение данных дашборда из кэша"""
        key = f"dashboard:{role}:{user_id}"
        return await self.get(key)
    
    async def invalidate_user_cache(self, user_id: int) -> int:
        """Очистка всего кэша пользователя"""
        pattern = f"*:{user_id}*"
        return await self.clear_pattern(pattern)
    
    async def cache_comments(
        self, 
        target_type: str, 
        target_id: int, 
        comments_data: list
    ) -> bool:
        """Кэширование комментариев"""
        key = f"comments:{target_type}:{target_id}"
        return await self.set(key, comments_data, settings.cache_comments_ttl)
    
    async def get_comments(
        self, 
        target_type: str, 
        target_id: int
    ) -> Optional[list]:
        """Получение комментариев из кэша"""
        key = f"comments:{target_type}:{target_id}"
        return await self.get(key)


# Глобальный экземпляр Redis клиента
redis_client = RedisClient()


# Для тестирования из командной строки
if __name__ == "__main__":
    async def main():
        print("🔄 Тестирование подключения к Redis...")
        
        await redis_client.connect()
        
        if redis_client.is_connected:
            print("✅ Подключение к Redis успешно!")
            
            # Тестируем базовые операции
            await redis_client.set("test_key", {"message": "Hello Redis!"}, 60)
            value = await redis_client.get("test_key")
            print(f"📝 Тест записи/чтения: {value}")
            
            await redis_client.delete("test_key")
            print("🗑️ Тестовый ключ удален")
        else:
            print("❌ Подключение к Redis не удалось!")
        
        await redis_client.disconnect()
    
    asyncio.run(main())