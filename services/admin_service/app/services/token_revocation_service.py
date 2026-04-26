"""
Сервис user-level отзыва JWT-токенов через Redis.

Используется в Admin Service после операций, изменяющих критичные данные
пользователя (роль, studio_id, активность). После отзыва все сервисы через
shared/auth_lib увидят, что старые токены невалидны.
"""

import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)


class TokenRevocationService:
    """Записывает user-level revocation в Redis."""
    
    USER_KEY_TEMPLATE = "user:{user_id}:revoked_after"
    
    def __init__(self) -> None:
        self._redis: Optional[redis_lib.Redis] = None
    
    async def _get_redis(self) -> redis_lib.Redis:
        if self._redis is None:
            self._redis = redis_lib.from_url(
                settings.jwt_blacklist_redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis
    
    async def revoke_all_user_tokens(
        self,
        user_id: int,
        reason: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Отозвать все access-токены пользователя."""
        if ttl_seconds is None:
            ttl_seconds = 30 * 60
        
        try:
            client = await self._get_redis()
            now_ts = int(datetime.utcnow().timestamp())
            key = self.USER_KEY_TEMPLATE.format(user_id=user_id)
            await client.set(key, str(now_ts), ex=ttl_seconds)
            logger.info(
                "User-level token revocation: user_id=%s reason=%s revoked_after=%s",
                user_id, reason, now_ts,
            )
        except Exception as exc:
            logger.error(
                "Failed to revoke user tokens: user_id=%s reason=%s error=%s",
                user_id, reason, exc,
            )


token_revocation_service = TokenRevocationService()