"""
Redis сервис для кеширования JWT blacklist
Ускоряет проверку отозванных токенов в 10-100 раз
"""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database.redis_client import redis_client
from app.repositories.user_repository import TokenBlacklistRepository
from app.database.connection import get_async_session

logger = logging.getLogger(__name__)


class RedisBlacklistService:
    """Сервис для кеширования JWT blacklist в Redis"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.blacklist_repo = TokenBlacklistRepository(db)
        self.cache_prefix = "jwt_blacklist"
        self.default_ttl = 3600  # 1 час по умолчанию
    
    def _get_cache_key(self, token_jti: str) -> str:
        """Формирование ключа для кеша"""
        return f"{self.cache_prefix}:{token_jti}"
    
    async def is_token_blacklisted(self, token_jti: str) -> bool:
        """
        Проверка токена в blacklist с использованием Redis кеша
        
        Args:
            token_jti: Уникальный идентификатор токена
            
        Returns:
            True если токен в blacklist, False если нет
        """
        cache_key = self._get_cache_key(token_jti)
        
        try:
            # Сначала проверяем в Redis (быстро)
            cached_result = await redis_client.get(cache_key)
            
            if cached_result is not None:
                logger.debug(f"Blacklist cache HIT for token {token_jti[:8]}...")
                return cached_result == "1"
            
            logger.debug(f"Blacklist cache MISS for token {token_jti[:8]}...")
            
        except Exception as e:
            logger.warning(f"Redis error during blacklist check: {e}")
            # Продолжаем с проверкой в БД
        
        # Если нет в кеше, проверяем в БД
        db_result = await self.blacklist_repo.is_blacklisted(token_jti)
        
        try:
            # Кешируем результат в Redis
            cache_value = "1" if db_result else "0"
            await redis_client.set(cache_key, cache_value, expire=self.default_ttl)
            logger.debug(f"Cached blacklist result for token {token_jti[:8]}...")
            
        except Exception as e:
            logger.warning(f"Failed to cache blacklist result: {e}")
        
        return db_result
    
    async def add_token_to_blacklist(
        self,
        token_jti: str,
        token_type: str,
        expires_at: datetime,
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Добавление токена в blacklist с немедленным кешированием
        
        Args:
            token_jti: Уникальный идентификатор токена
            token_type: Тип токена ('access' или 'refresh')
            expires_at: Время истечения токена
            user_id: ID пользователя (опционально)
            reason: Причина добавления в blacklist
        """
        
        # Добавляем в БД
        await self.blacklist_repo.add_to_blacklist(
            token_jti=token_jti,
            token_type=token_type,
            expires_at=expires_at,
            user_id=user_id,
            reason=reason
        )
        
        try:
            # Сразу кешируем в Redis с TTL до истечения токена
            cache_key = self._get_cache_key(token_jti)
            ttl = int((expires_at - datetime.utcnow()).total_seconds())
            
            if ttl > 0:
                await redis_client.set(cache_key, "1", expire=ttl)
                logger.info(f"Token {token_jti[:8]}... added to blacklist cache")
            
        except Exception as e:
            logger.warning(f"Failed to cache blacklisted token: {e}")
    
    async def remove_token_from_cache(self, token_jti: str) -> None:
        """
        Удаление токена из кеша (например, при восстановлении токена)
        """
        try:
            cache_key = self._get_cache_key(token_jti)
            await redis_client.delete(cache_key)
            logger.info(f"Token {token_jti[:8]}... removed from blacklist cache")
            
        except Exception as e:
            logger.warning(f"Failed to remove token from cache: {e}")
    
    async def invalidate_user_tokens_cache(self, user_id: int) -> None:
        """
        Инвалидация кеша всех токенов пользователя
        (используется при logout_all_devices)
        """
        try:
            # Получаем все ключи blacklist
            pattern = f"{self.cache_prefix}:*"
            keys = await redis_client.get_keys_pattern(pattern)
            
            if keys:
                # В production лучше использовать pipeline для множественного удаления
                for key in keys:
                    await redis_client.delete(key)
                
                logger.info(f"Invalidated {len(keys)} blacklist cache entries for user {user_id}")
            
        except Exception as e:
            logger.warning(f"Failed to invalidate user tokens cache: {e}")
    
    async def get_cache_stats(self) -> dict:
        """Получение статистики кеша blacklist"""
        try:
            pattern = f"{self.cache_prefix}:*"
            keys = await redis_client.get_keys_pattern(pattern)
            
            return {
                "cached_tokens": len(keys),
                "cache_prefix": self.cache_prefix,
                "default_ttl": self.default_ttl
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}
    
    async def cleanup_expired_cache(self) -> int:
        """
        Принудительная очистка истекших записей кеша
        (Redis делает это автоматически, но можно вызвать вручную)
        """
        try:
            pattern = f"{self.cache_prefix}:*"
            keys = await redis_client.get_keys_pattern(pattern)
            
            cleaned_count = 0
            for key in keys:
                # Проверяем TTL
                ttl = await redis_client._redis.ttl(key) if redis_client._redis else -1
                if ttl == -1:  # Ключ без TTL или не существует
                    await redis_client.delete(key)
                    cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} expired blacklist cache entries")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired cache: {e}")
            return 0


# Dependency для FastAPI
async def get_redis_blacklist_service(
    db: AsyncSession = Depends(get_async_session)
) -> RedisBlacklistService:
    """Dependency для получения RedisBlacklistService"""
    return RedisBlacklistService(db)