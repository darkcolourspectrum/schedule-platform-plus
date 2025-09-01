"""
Redis Rate Limiter для защиты от брутфорса и DDoS
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from app.database.redis_client import redis_client
from app.core.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """Сервис rate limiting с использованием Redis"""
    
    def __init__(self):
        self.prefix = "rate_limit"
    
    def _get_key(self, identifier: str, endpoint: str = "") -> str:
        """Формирование ключа для rate limiting"""
        if endpoint:
            return f"{self.prefix}:{endpoint}:{identifier}"
        return f"{self.prefix}:{identifier}"
    
    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        endpoint: str = ""
    ) -> Dict[str, Any]:
        """
        Проверка rate limit с использованием sliding window
        
        Args:
            identifier: Уникальный идентификатор (IP, email, user_id)
            limit: Максимальное количество запросов
            window_seconds: Временное окно в секундах
            endpoint: Название endpoint для группировки
            
        Returns:
            Dict с информацией о лимите
        """
        
        key = self._get_key(identifier, endpoint)
        
        try:
            # Используем Redis INCR для атомарного инкремента
            current_count = await redis_client.increment(key)
            
            if current_count == 1:
                # Первый запрос в окне - устанавливаем TTL
                await redis_client.expire(key, window_seconds)
                ttl = window_seconds
            else:
                # Получаем оставшееся время окна
                ttl = await redis_client._redis.ttl(key) if redis_client._redis else window_seconds
                if ttl == -1:  # Ключ без TTL (не должно происходить)
                    await redis_client.expire(key, window_seconds)
                    ttl = window_seconds
            
            is_allowed = current_count <= limit
            
            result = {
                "allowed": is_allowed,
                "current_count": current_count,
                "limit": limit,
                "window_seconds": window_seconds,
                "ttl_seconds": ttl,
                "reset_time": datetime.utcnow() + timedelta(seconds=ttl)
            }
            
            if not is_allowed:
                logger.warning(
                    f"Rate limit exceeded for {identifier} on {endpoint or 'global'}: "
                    f"{current_count}/{limit} requests in {window_seconds}s window"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Redis rate limiter error: {e}")
            # Fallback: разрешаем запрос при ошибке Redis
            return {
                "allowed": True,
                "current_count": 0,
                "limit": limit,
                "window_seconds": window_seconds,
                "ttl_seconds": window_seconds,
                "reset_time": datetime.utcnow() + timedelta(seconds=window_seconds),
                "error": str(e)
            }
    
    async def enforce_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        endpoint: str = ""
    ) -> None:
        """
        Проверка rate limit с выбросом исключения при превышении
        
        Raises:
            RateLimitExceededException: При превышении лимита
        """
        
        result = await self.check_rate_limit(identifier, limit, window_seconds, endpoint)
        
        if not result["allowed"]:
            raise RateLimitExceededException(retry_after=result["ttl_seconds"])
    
    async def reset_rate_limit(self, identifier: str, endpoint: str = "") -> bool:
        """Сброс rate limit для идентификатора"""
        try:
            key = self._get_key(identifier, endpoint)
            deleted = await redis_client.delete(key)
            
            if deleted:
                logger.info(f"Rate limit reset for {identifier} on {endpoint or 'global'}")
            
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False
    
    async def get_rate_limit_status(
        self,
        identifier: str,
        endpoint: str = ""
    ) -> Dict[str, Any]:
        """Получение текущего статуса rate limit"""
        try:
            key = self._get_key(identifier, endpoint)
            current_count = await redis_client.get(key)
            
            if current_count is None:
                return {
                    "current_count": 0,
                    "ttl_seconds": 0,
                    "active": False
                }
            
            ttl = await redis_client._redis.ttl(key) if redis_client._redis else 0
            
            return {
                "current_count": int(current_count),
                "ttl_seconds": ttl,
                "active": True,
                "reset_time": datetime.utcnow() + timedelta(seconds=ttl) if ttl > 0 else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {"error": str(e)}


class AuthRateLimiter:
    """Специализированный rate limiter для auth endpoints"""
    
    def __init__(self):
        self.limiter = RedisRateLimiter()
        
        # Настройки лимитов для разных операций
        self.limits = {
            "login_email": {"limit": 5, "window": 300},      # 5 попыток входа с email за 5 минут
            "login_ip": {"limit": 20, "window": 300},        # 20 попыток входа с IP за 5 минут
            "register_ip": {"limit": 3, "window": 3600},     # 3 регистрации с IP за час
            "refresh_token": {"limit": 30, "window": 60},    # 30 обновлений токена в минуту
            "password_reset": {"limit": 3, "window": 3600},  # 3 сброса пароля за час
            "global_ip": {"limit": 100, "window": 60}        # 100 запросов с IP в минуту
        }
    
    async def check_login_rate_limit(self, email: str, ip_address: str) -> None:
        """Проверка лимитов для входа в систему"""
        
        # Лимит по email
        email_config = self.limits["login_email"]
        await self.limiter.enforce_rate_limit(
            identifier=email,
            limit=email_config["limit"],
            window_seconds=email_config["window"],
            endpoint="login_email"
        )
        
        # Лимит по IP
        ip_config = self.limits["login_ip"]
        await self.limiter.enforce_rate_limit(
            identifier=ip_address,
            limit=ip_config["limit"],
            window_seconds=ip_config["window"],
            endpoint="login_ip"
        )
    
    async def check_register_rate_limit(self, ip_address: str) -> None:
        """Проверка лимитов для регистрации"""
        
        config = self.limits["register_ip"]
        await self.limiter.enforce_rate_limit(
            identifier=ip_address,
            limit=config["limit"],
            window_seconds=config["window"],
            endpoint="register"
        )
    
    async def check_refresh_rate_limit(self, user_id: int) -> None:
        """Проверка лимитов для обновления токена"""
        
        config = self.limits["refresh_token"]
        await self.limiter.enforce_rate_limit(
            identifier=str(user_id),
            limit=config["limit"],
            window_seconds=config["window"],
            endpoint="refresh"
        )
    
    async def check_global_rate_limit(self, ip_address: str) -> None:
        """Глобальный лимит запросов с IP"""
        
        config = self.limits["global_ip"]
        await self.limiter.enforce_rate_limit(
            identifier=ip_address,
            limit=config["limit"],
            window_seconds=config["window"],
            endpoint="global"
        )
    
    async def reset_failed_login_attempts(self, email: str, ip_address: str) -> None:
        """Сброс счетчиков при успешном входе"""
        
        await self.limiter.reset_rate_limit(email, "login_email")
        # IP лимит не сбрасываем - оставляем для защиты от распределенных атак
    
    async def get_login_attempts_info(self, email: str, ip_address: str) -> Dict[str, Any]:
        """Получение информации о попытках входа"""
        
        email_status = await self.limiter.get_rate_limit_status(email, "login_email")
        ip_status = await self.limiter.get_rate_limit_status(ip_address, "login_ip")
        
        return {
            "email_attempts": email_status,
            "ip_attempts": ip_status,
            "email_limit": self.limits["login_email"],
            "ip_limit": self.limits["login_ip"]
        }
    
    async def get_rate_limit_stats(self) -> Dict[str, Any]:
        """Получение общей статистики rate limiting"""
        try:
            # Получаем все ключи rate limiting
            pattern = "rate_limit:*"
            keys = await redis_client.get_keys_pattern(pattern)
            
            stats = {
                "total_limited_identifiers": len(keys),
                "active_endpoints": {},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Группируем по endpoints
            for key in keys:
                parts = key.split(":")
                if len(parts) >= 3:
                    endpoint = parts[1]
                    if endpoint not in stats["active_endpoints"]:
                        stats["active_endpoints"][endpoint] = 0
                    stats["active_endpoints"][endpoint] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get rate limit stats: {e}")
            return {"error": str(e)}


# Глобальный экземпляр для использования в приложении
auth_rate_limiter = AuthRateLimiter()


# Dependency для FastAPI
async def get_auth_rate_limiter() -> AuthRateLimiter:
    """Dependency для получения AuthRateLimiter"""
    return auth_rate_limiter