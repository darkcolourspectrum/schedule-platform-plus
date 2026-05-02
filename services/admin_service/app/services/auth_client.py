"""
HTTP-клиент для общения Admin Service с Auth Service.

Используется для admin-операций над пользователями: смена роли,
активация/деактивация, привязка к студии. Auth Service в ответ на эти
вызовы публикует события в outbox, которые приходят к нам обратно через
consumer и обновляют локальный users_cache.

Все вызовы используют X-Internal-API-Key для аутентификации между сервисами.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AuthServiceError(Exception):
    """Базовая ошибка Auth Service клиента."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AuthServiceUserNotFound(AuthServiceError):
    """Пользователь не найден в Auth Service."""


class AuthServiceClient:
    """HTTP-клиент к Auth Service для admin-операций."""
    
    def __init__(self):
        self.base_url = settings.auth_service_url
        self.timeout = 10.0
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-API-Key": settings.internal_api_key,
        }
    
    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Выполнить HTTP-запрос к Auth Service.
        
        Raises:
            AuthServiceUserNotFound: если 404
            AuthServiceError: для других неуспешных ответов
        """
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json,
                )
        except httpx.RequestError as exc:
            logger.error("Auth Service network error: %s %s err=%s", method, path, exc)
            raise AuthServiceError(f"Network error calling Auth Service: {exc}") from exc
        
        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 404:
            logger.warning("Auth Service 404: %s %s", method, path)
            raise AuthServiceUserNotFound(f"User not found at {path}")
        
        logger.error(
            "Auth Service error: %s %s status=%s body=%s",
            method, path, response.status_code, response.text,
        )
        raise AuthServiceError(
            f"Auth Service returned {response.status_code}: {response.text}",
            status_code=response.status_code,
        )
    
    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """Получить пользователя по ID. Возвращает UserProfile."""
        return await self._request("GET", f"/api/v1/users/{user_id}")
    
    async def change_role(self, user_id: int, role_name: str) -> Dict[str, Any]:
        """
        Изменить роль пользователя.
        
        Auth Service применит изменение в БД и опубликует событие role.changed
        в outbox, которое мы получим через consumer и применим к users_cache.
        """
        return await self._request(
            "PUT",
            f"/api/v1/users/{user_id}/role",
            json={"role": role_name},
        )
    
    async def assign_studio(self, user_id: int, studio_id: int) -> Dict[str, Any]:
        """Привязать пользователя к студии."""
        return await self._request(
            "PUT",
            f"/api/v1/users/{user_id}/studio",
            json={"studio_id": studio_id},
        )
    
    async def activate(self, user_id: int) -> Dict[str, Any]:
        """Активировать пользователя."""
        return await self._request(
            "POST",
            f"/api/v1/users/{user_id}/activate",
        )
    
    async def deactivate(self, user_id: int) -> Dict[str, Any]:
        """Деактивировать пользователя."""
        return await self._request(
            "POST",
            f"/api/v1/users/{user_id}/deactivate",
        )


# Глобальный singleton клиента
auth_client = AuthServiceClient()