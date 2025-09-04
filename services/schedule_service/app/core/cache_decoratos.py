"""
Декораторы для кэширования с использованием Redis
Замена lru_cache с поддержкой TTL
"""

import functools
import logging
from typing import Callable, Any, Optional, Union
import hashlib
import json

from app.database.redis_client import redis_client

logger = logging.getLogger(__name__)


def redis_cache(
    ttl: int = 300,  # TTL в секундах (по умолчанию 5 минут)
    prefix: str = "cache",
    key_builder: Optional[Callable] = None
):
    """
    Декоратор для кэширования результатов функций в Redis с TTL
    
    Args:
        ttl: Время жизни кэша в секундах
        prefix: Префикс для ключей кэша
        key_builder: Функция для построения ключа кэша
    
    Example:
        @redis_cache(ttl=600, prefix="user_info")
        async def get_user_info(user_id: int):
            # Дорогая операция
            return {"id": user_id, "name": "User"}
    """
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Построение ключа кэша
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _build_default_key(func.__name__, prefix, *args, **kwargs)
            
            try:
                # Пробуем получить из кэша
                cached_result = await redis_client.get_json(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache HIT for key: {cache_key}")
                    return cached_result
                
                # Выполняем функцию
                logger.debug(f"Cache MISS for key: {cache_key}")
                result = await func(*args, **kwargs)
                
                # Кэшируем результат
                if result is not None:
                    await redis_client.set(cache_key, result, expire=ttl)
                    logger.debug(f"Cached result for key: {cache_key} (TTL: {ttl}s)")
                
                return result
                
            except Exception as e:
                logger.error(f"Redis cache error for {func.__name__}: {e}")
                # При ошибках кэша выполняем функцию без кэширования
                return await func(*args, **kwargs)
        
        # Добавляем методы для управления кэшем
        wrapper.cache_key_builder = lambda *args, **kwargs: (
            key_builder(*args, **kwargs) if key_builder 
            else _build_default_key(func.__name__, prefix, *args, **kwargs)
        )
        wrapper.invalidate = lambda *args, **kwargs: _invalidate_cache(
            wrapper.cache_key_builder(*args, **kwargs)
        )
        
        return wrapper
    
    return decorator


def _build_default_key(func_name: str, prefix: str, *args, **kwargs) -> str:
    """Построение ключа кэша по умолчанию"""
    try:
        # Создаем строку из аргументов
        args_str = "_".join(str(arg) for arg in args)
        kwargs_str = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        
        # Объединяем все части
        key_parts = [prefix, func_name]
        if args_str:
            key_parts.append(args_str)
        if kwargs_str:
            key_parts.append(kwargs_str)
        
        cache_key = ":".join(key_parts)
        
        # Если ключ слишком длинный, используем хэш
        if len(cache_key) > 200:
            hash_input = f"{func_name}:{args_str}:{kwargs_str}"
            hash_key = hashlib.md5(hash_input.encode()).hexdigest()
            cache_key = f"{prefix}:{func_name}:{hash_key}"
        
        return cache_key
        
    except Exception as e:
        logger.error(f"Error building cache key: {e}")
        # Fallback к хэшу от имени функции
        return f"{prefix}:{func_name}:fallback"


async def _invalidate_cache(cache_key: str) -> bool:
    """Инвалидация конкретного ключа кэша"""
    try:
        result = await redis_client.delete(cache_key)
        if result:
            logger.info(f"Cache invalidated for key: {cache_key}")
        return result
    except Exception as e:
        logger.error(f"Error invalidating cache key {cache_key}: {e}")
        return False


class CacheManager:
    """Менеджер для управления кэшем приложения"""
    
    @staticmethod
    async def invalidate_pattern(pattern: str) -> int:
        """
        Инвалидация кэша по шаблону
        
        Args:
            pattern: Шаблон для поиска ключей (например, "user_info:*")
            
        Returns:
            Количество удаленных ключей
        """
        try:
            return await redis_client.clear_pattern(pattern)
        except Exception as e:
            logger.error(f"Error invalidating cache pattern {pattern}: {e}")
            return 0
    
    @staticmethod
    async def get_stats() -> dict:
        """Получение статистики кэша"""
        try:
            cache_keys = await redis_client.get_keys_pattern("cache:*")
            
            stats = {
                "total_cache_keys": len(cache_keys),
                "cache_prefixes": {}
            }
            
            # Группируем по префиксам
            for key in cache_keys:
                parts = key.split(":")
                if len(parts) >= 2:
                    prefix = parts[1]  # После cache:
                    stats["cache_prefixes"][prefix] = stats["cache_prefixes"].get(prefix, 0) + 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    @staticmethod
    async def clear_all_cache() -> bool:
        """Очистка всего кэша приложения (только для development)"""
        try:
            deleted = await redis_client.clear_pattern("cache:*")
            logger.warning(f"Cleared {deleted} cache entries")
            return deleted > 0
        except Exception as e:
            logger.error(f"Error clearing all cache: {e}")
            return False


# Готовые декораторы для частых случаев использования

def cache_user_info(ttl: int = 300):
    """Кэширование информации о пользователе"""
    return redis_cache(
        ttl=ttl,
        prefix="user_info",
        key_builder=lambda user_id, *args, **kwargs: f"user_info:{user_id}"
    )


def cache_studio_info(ttl: int = 600):
    """Кэширование информации о студии"""
    return redis_cache(
        ttl=ttl,
        prefix="studio_info", 
        key_builder=lambda studio_id, *args, **kwargs: f"studio_info:{studio_id}"
    )


def cache_schedule_data(ttl: int = 180):
    """Кэширование данных расписания"""
    return redis_cache(
        ttl=ttl,
        prefix="schedule_data"
    )


# Глобальный менеджер кэша
cache_manager = CacheManager()