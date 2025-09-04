"""
Модуль для подключения и работы с Redis
Обеспечивает кэширование данных в Profile Service
"""

import json
import logging
from typing import Any, Optional, Union
import redis.asyncio as redis
from redis.asyncio import ConnectionPool
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Менеджер для работы с Redis"""
    
    def __init__(self):
        self._pool = None
        self._client = None
    
    @property
    def pool(self) -> ConnectionPool:
        """Получение пула подключений Redis"""
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
                retry_on_timeout=True
            )
            logger.info("Пул подключений Redis создан")
        return self._pool
    
    @property
    def client(self) -> redis.Redis:
        """Получение Redis клиента"""
        if self._client is None:
            self._client = redis.Redis(connection_pool=self.pool)
            logger.info("Redis клиент создан")
        return self._client
    
    async def check_connection(self) -> bool:
        """Проверка подключения к Redis"""
        try:
            await self.client.ping()
            return True
        except RedisError as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            return False
    
    async def get_info(self) -> dict:
        """Получение информации о Redis сервере"""
        try:
            info = await self.client.info()
            return {
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "status": "connected"
            }
        except RedisError as e:
            logger.error(f"Ошибка получения информации Redis: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def set_json(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        Сохранение JSON данных в Redis с опциональным TTL
        
        Args:
            key: Ключ для сохранения
            value: Данные для сериализации в JSON
            expire: Время жизни в секундах (опционально)
        
        Returns:
            bool: Успех операции
        """
        try:
            json_data = json.dumps(value, ensure_ascii=False, default=str)
            if expire:
                await self.client.setex(key, expire, json_data)
            else:
                await self.client.set(key, json_data)
            return True
        except (RedisError, json.JSONEncodeError) as e:
            logger.error(f"Ошибка записи JSON в Redis (key: {key}): {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Any]:
        """
        Получение и десериализация JSON данных из Redis
        
        Args:
            key: Ключ для получения данных
        
        Returns:
            Десериализованные данные или None если ключ не найден
        """
        try:
            json_data = await self.client.get(key)
            if json_data is None:
                return None
            return json.loads(json_data)
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка чтения JSON из Redis (key: {key}): {e}")
            return None
    
    async def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """
        Сохранение строки в Redis
        
        Args:
            key: Ключ
            value: Значение
            expire: Время жизни в секундах
        
        Returns:
            bool: Успех операции
        """
        try:
            if expire:
                await self.client.setex(key, expire, value)
            else:
                await self.client.set(key, value)
            return True
        except RedisError as e:
            logger.error(f"Ошибка записи в Redis (key: {key}): {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """
        Получение строки из Redis
        
        Args:
            key: Ключ
        
        Returns:
            Значение или None если ключ не найден
        """
        try:
            return await self.client.get(key)
        except RedisError as e:
            logger.error(f"Ошибка чтения из Redis (key: {key}): {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """
        Удаление ключа из Redis
        
        Args:
            key: Ключ для удаления
        
        Returns:
            bool: Успех операции
        """
        try:
            result = await self.client.delete(key)
            return result > 0
        except RedisError as e:
            logger.error(f"Ошибка удаления из Redis (key: {key}): {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Проверка существования ключа
        
        Args:
            key: Ключ для проверки
        
        Returns:
            bool: Существует ли ключ
        """
        try:
            return await self.client.exists(key) > 0
        except RedisError as e:
            logger.error(f"Ошибка проверки ключа Redis (key: {key}): {e}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """
        Установка времени жизни для существующего ключа
        
        Args:
            key: Ключ
            seconds: Время жизни в секундах
        
        Returns:
            bool: Успех операции
        """
        try:
            return await self.client.expire(key, seconds)
        except RedisError as e:
            logger.error(f"Ошибка установки TTL Redis (key: {key}): {e}")
            return False
    
    async def keys_by_pattern(self, pattern: str) -> list:
        """
        Получение ключей по паттерну
        
        Args:
            pattern: Паттерн поиска (например, "user:*")
        
        Returns:
            Список найденных ключей
        """
        try:
            return await self.client.keys(pattern)
        except RedisError as e:
            logger.error(f"Ошибка поиска ключей Redis (pattern: {pattern}): {e}")
            return []
    
    async def delete_by_pattern(self, pattern: str) -> int:
        """
        Удаление ключей по паттерну
        
        Args:
            pattern: Паттерн поиска (например, "user:*")
        
        Returns:
            Количество удаленных ключей
        """
        try:
            keys = await self.keys_by_pattern(pattern)
            if keys:
                return await self.client.delete(*keys)
            return 0
        except RedisError as e:
            logger.error(f"Ошибка удаления ключей Redis (pattern: {pattern}): {e}")
            return 0
    
    async def close(self):
        """Закрытие соединений с Redis"""
        if self._client:
            await self._client.close()
            logger.info("Подключения к Redis закрыты")


class CacheService:
    """Сервис для кэширования с префиксами ключей"""
    
    def __init__(self, redis_manager: RedisManager):
        self.redis = redis_manager
        self.prefix = "profile_service"
    
    def _make_key(self, key: str, namespace: str = "") -> str:
        """Создание ключа с префиксом"""
        if namespace:
            return f"{self.prefix}:{namespace}:{key}"
        return f"{self.prefix}:{key}"
    
    # Методы для кэширования пользователей
    async def set_user(self, user_id: int, user_data: dict, ttl: Optional[int] = None) -> bool:
        """Кэширование данных пользователя"""
        key = self._make_key(str(user_id), "user")
        expire_time = ttl or settings.user_cache_ttl
        return await self.redis.set_json(key, user_data, expire_time)
    
    async def get_user(self, user_id: int) -> Optional[dict]:
        """Получение данных пользователя из кэша"""
        key = self._make_key(str(user_id), "user")
        return await self.redis.get_json(key)
    
    async def delete_user(self, user_id: int) -> bool:
        """Удаление пользователя из кэша"""
        key = self._make_key(str(user_id), "user")
        return await self.redis.delete(key)
    
    # Методы для кэширования расписания
    async def set_user_schedule(self, user_id: int, schedule_data: dict, ttl: Optional[int] = None) -> bool:
        """Кэширование расписания пользователя"""
        key = self._make_key(str(user_id), "schedule")
        expire_time = ttl or settings.schedule_cache_ttl
        return await self.redis.set_json(key, schedule_data, expire_time)
    
    async def get_user_schedule(self, user_id: int) -> Optional[dict]:
        """Получение расписания пользователя из кэша"""
        key = self._make_key(str(user_id), "schedule")
        return await self.redis.get_json(key)
    
    async def delete_user_schedule(self, user_id: int) -> bool:
        """Удаление расписания пользователя из кэша"""
        key = self._make_key(str(user_id), "schedule")
        return await self.redis.delete(key)
    
    # Методы для кэширования профилей
    async def set_profile(self, user_id: int, profile_data: dict, ttl: Optional[int] = None) -> bool:
        """Кэширование профиля пользователя"""
        key = self._make_key(str(user_id), "profile")
        expire_time = ttl or settings.cache_ttl
        return await self.redis.set_json(key, profile_data, expire_time)
    
    async def get_profile(self, user_id: int) -> Optional[dict]:
        """Получение профиля пользователя из кэша"""
        key = self._make_key(str(user_id), "profile")
        return await self.redis.get_json(key)
    
    async def delete_profile(self, user_id: int) -> bool:
        """Удаление профиля пользователя из кэша"""
        key = self._make_key(str(user_id), "profile")
        return await self.redis.delete(key)
    
    # Методы для кэширования дашбордов
    async def set_dashboard(self, user_id: int, dashboard_data: dict, ttl: Optional[int] = None) -> bool:
        """Кэширование дашборда пользователя"""
        key = self._make_key(str(user_id), "dashboard")
        expire_time = ttl or settings.cache_ttl
        return await self.redis.set_json(key, dashboard_data, expire_time)
    
    async def get_dashboard(self, user_id: int) -> Optional[dict]:
        """Получение дашборда пользователя из кэша"""
        key = self._make_key(str(user_id), "dashboard")
        return await self.redis.get_json(key)
    
    async def delete_dashboard(self, user_id: int) -> bool:
        """Удаление дашборда пользователя из кэша"""
        key = self._make_key(str(user_id), "dashboard")
        return await self.redis.delete(key)
    
    # Инвалидация кэша
    async def invalidate_user_cache(self, user_id: int) -> int:
        """Полная инвалидация кэша пользователя"""
        pattern = self._make_key(str(user_id), "*")
        return await self.redis.delete_by_pattern(pattern)
    
    async def clear_all_cache(self) -> int:
        """Очистка всего кэша сервиса"""
        pattern = f"{self.prefix}:*"
        return await self.redis.delete_by_pattern(pattern)


# Создание глобальных экземпляров
redis_manager = RedisManager()
cache_service = CacheService(redis_manager)


if __name__ == "__main__":
    """Тестирование подключения к Redis"""
    import asyncio
    
    async def test_redis():
        """Тест подключения к Redis"""
        print("Тестирование подключения к Redis...")
        
        # Проверка подключения
        is_connected = await redis_manager.check_connection()
        print(f"Статус подключения: {'✓ Подключено' if is_connected else '✗ Ошибка подключения'}")
        
        if is_connected:
            # Получение информации о Redis
            redis_info = await redis_manager.get_info()
            print(f"Версия Redis: {redis_info.get('redis_version')}")
            print(f"Подключенные клиенты: {redis_info.get('connected_clients')}")
            print(f"Используемая память: {redis_info.get('used_memory_human')}")
            
            # Тест записи и чтения
            test_key = "test_key"
            test_data = {"message": "Привет из Profile Service!", "timestamp": "2025-09-05"}
            
            # Запись
            success = await redis_manager.set_json(test_key, test_data, 60)
            print(f"Тест записи: {'✓ Успешно' if success else '✗ Ошибка'}")
            
            # Чтение
            retrieved_data = await redis_manager.get_json(test_key)
            print(f"Тест чтения: {'✓ Успешно' if retrieved_data == test_data else '✗ Ошибка'}")
            
            # Удаление
            deleted = await redis_manager.delete(test_key)
            print(f"Тест удаления: {'✓ Успешно' if deleted else '✗ Ошибка'}")
        
        await redis_manager.close()
    
    asyncio.run(test_redis())