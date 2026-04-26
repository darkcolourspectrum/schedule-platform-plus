"""
Проверка отзыва JWT-токенов через Redis.

Поддерживает два уровня отзыва:
1. По jti — отозван конкретный токен (logout одного устройства)
2. По user_id — отозваны все токены пользователя, выданные до момента отзыва
   (logout-all, смена роли, деактивация)

Стратегия отказа: fail-open. Если Redis недоступен, проверка не выполняется
и токен считается не отозванным. В production это компромисс между
доступностью и безопасностью; warning-лог обязателен для мониторинга.
"""

import logging
from typing import Optional, Protocol

from shared.auth_lib.schemas import TokenPayload

logger = logging.getLogger(__name__)


class RedisClientProtocol(Protocol):
    """
    Минимальный интерфейс Redis-клиента, который требуется этому модулю.
    Совместим с redis.asyncio.Redis и любым асинхронным Redis-клиентом,
    реализующим методы exists() и get().
    """
    
    async def exists(self, *keys: str) -> int: ...
    async def get(self, key: str) -> Optional[bytes]: ...


class BlacklistChecker:
    """
    Проверка отзыва JWT-токенов через Redis.
    
    Используется в каждом сервисе. Создаётся один раз с redis-клиентом
    и применяется в dependency get_current_user после успешного декодирования.
    
    Ключи в Redis:
        jwt_blacklist:{jti}              - отзыв конкретного токена
        user:{user_id}:revoked_after     - timestamp отзыва всех токенов юзера
    """
    
    JTI_KEY_PREFIX = "jwt_blacklist:"
    USER_KEY_TEMPLATE = "user:{user_id}:revoked_after"
    
    def __init__(self, redis_client: RedisClientProtocol, fail_open: bool = True):
        """
        Args:
            redis_client: Асинхронный Redis-клиент.
            fail_open: Поведение при недоступности Redis.
                True (по умолчанию) — пропускать запрос с предупреждением в логе.
                False — считать токен отозванным (более параноидально).
        """
        self._redis = redis_client
        self._fail_open = fail_open
    
    async def is_revoked(self, payload: TokenPayload) -> bool:
        """
        Проверить, отозван ли токен.
        
        Args:
            payload: Уже декодированный и валидный по подписи payload.
        
        Returns:
            True если токен отозван (logout/смена роли/деактивация).
            False если токен не отозван либо Redis недоступен (fail-open).
        """
        try:
            if await self._is_jti_blacklisted(payload.jti):
                logger.info(
                    "Token revoked by jti: jti=%s user_id=%s",
                    payload.jti, payload.user_id,
                )
                return True
            
            if await self._is_user_revoked(payload.user_id, payload.iat):
                logger.info(
                    "Token revoked by user-level revocation: user_id=%s iat=%s",
                    payload.user_id, payload.iat,
                )
                return True
            
            return False
        
        except Exception as exc:
            if self._fail_open:
                logger.warning(
                    "Blacklist check failed, falling open. "
                    "user_id=%s jti=%s error=%s",
                    payload.user_id, payload.jti, exc,
                )
                return False
            else:
                logger.error(
                    "Blacklist check failed, failing closed. "
                    "user_id=%s jti=%s error=%s",
                    payload.user_id, payload.jti, exc,
                )
                return True
    
    async def _is_jti_blacklisted(self, jti: str) -> bool:
        """Проверка отзыва конкретного токена по jti."""
        key = f"{self.JTI_KEY_PREFIX}{jti}"
        result = await self._redis.exists(key)
        return result > 0
    
    async def _is_user_revoked(self, user_id: int, token_iat: int) -> bool:
        """
        Проверка user-level отзыва.
        
        Если в Redis есть ключ user:{user_id}:revoked_after со значением T,
        то любой токен пользователя с iat < T считается отозванным.
        """
        key = self.USER_KEY_TEMPLATE.format(user_id=user_id)
        raw_value = await self._redis.get(key)
        
        if raw_value is None:
            return False
        
        try:
            revoked_after = int(raw_value)
        except (ValueError, TypeError):
            logger.warning(
                "Malformed revoked_after value in Redis: key=%s value=%r",
                key, raw_value,
            )
            return False
        
        return token_iat < revoked_after