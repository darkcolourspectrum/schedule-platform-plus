import redis.asyncio as redis
from redis.asyncio import Redis
import logging
from typing import Optional, Union
import json
from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)


class RedisClient:
    """
    Асинхронный Redis клиент для кэширования расписания
    """
    
    def __init__(self):
        self._redis: Optional[Redis] = None
    
    async def connect(self) -> None:
        """Подключение к Redis"""
        try:
            self._redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            
            # Тест подключения
            await self._redis.ping()
            logger.info("Подключение к Redis успешно!")
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Отключение от Redis"""
        if self._redis:
            await self._redis.close()
            logger.info("Соединение с Redis закрыто")
    
    async def get(self, key: str) -> Optional[str]:
        """Получение значения по ключу"""
        try:
            if not self._redis:
                await self.connect()
            return await self._redis.get(key)
        except Exception as e:
            logger.error(f"Ошибка получения из Redis key={key}: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: Union[str, dict, list],
        expire: Optional[int] = None
    ) -> bool:
        """
        Сохранение значения с опциональным TTL
        
        Args:
            key: Ключ
            value: Значение (строка, dict или list)
            expire: TTL в секундах
        """
        try:
            if not self._redis:
                await self.connect()
            
            # Сериализуем сложные типы в JSON
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            if expire:
                return await self._redis.setex(key, expire, value)
            else:
                return await self._redis.set(key, value)
                
        except Exception as e:
            logger.error(f"Ошибка сохранения в Redis key={key}: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Union[dict, list]]:
        """Получение и десериализация JSON значения"""
        try:
            value = await self.get(key)
            if value:
                return json.loads(value)
            return None
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Ошибка десериализации JSON key={key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Удаление ключа"""
        try:
            if not self._redis:
                await self.connect()
            return bool(await self._redis.delete(key))
        except Exception as e:
            logger.error(f"Ошибка удаления из Redis key={key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        try:
            if not self._redis:
                await self.connect()
            return bool(await self._redis.exists(key))
        except Exception as e:
            logger.error(f"Ошибка проверки существования key={key}: {e}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Установка TTL для существующего ключа"""
        try:
            if not self._redis:
                await self.connect()
            return bool(await self._redis.expire(key, seconds))
        except Exception as e:
            logger.error(f"Ошибка установки TTL key={key}: {e}")
            return False
    
    async def get_keys_pattern(self, pattern: str) -> list:
        """Получение ключей по паттерну"""
        try:
            if not self._redis:
                await self.connect()
            return await self._redis.keys(pattern)
        except Exception as e:
            logger.error(f"Ошибка получения ключей по паттерну {pattern}: {e}")
            return []
    
    async def flush_db(self) -> bool:
        """Очистка текущей базы данных (только для development!)"""
        try:
            if not self._redis:
                await self.connect()
            
            if not settings.is_development:
                logger.warning("Очистка Redis разрешена только в development режиме!")
                return False
            
            await self._redis.flushdb()
            logger.info("База данных Redis очищена")
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки Redis: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Тестирование подключения к Redis"""
        try:
            if not self._redis:
                await self.connect()
            
            # Тест записи/чтения
            test_key = "test_connection_schedule"
            test_value = "test_value"
            
            await self.set(test_key, test_value, expire=10)
            result = await self.get(test_key)
            await self.delete(test_key)
            
            if result == test_value:
                logger.info("Redis работает корректно!")
                return True
            else:
                logger.error("Redis: ошибка записи/чтения")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка тестирования Redis: {e}")
            return False


# Глобальный экземпляр Redis клиента
redis_client = RedisClient()


# Dependency для FastAPI
async def get_redis_client() -> RedisClient:
    """Dependency для получения Redis клиента в endpoints"""
    if not redis_client._redis:
        await redis_client.connect()
    return redis_client


if __name__ == "__main__":
    """
    Скрипт для тестирования подключения к Redis
    Запуск: python -m app.database.redis_client
    """
    import asyncio
    
    async def main():
        print("Тестирование подключения к Redis...")
        print(f"URL: {settings.redis_url}")
        print(f"DB: {settings.redis_db}")
        print("-" * 50)
        
        client = RedisClient()
        
        # Тест подключения
        is_connected = await client.test_connection()
        
        if is_connected:
            print("\nRedis подключен и готов к работе!")
        else:
            print("\nRedis недоступен, но Schedule Service может работать без кеширования")
        
        # Закрываем соединение
        await client.disconnect()
        
        return is_connected
    
    # Запуск тестирования
    result = asyncio.run(main())
    if result:
        print("\nВсе проверки Redis пройдены успешно!")
    else:
        print("\nRedis недоступен, но это не критично для разработки")
        exit(1)