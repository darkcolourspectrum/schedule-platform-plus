"""
HTTP-клиент к Auth Service (internal API, X-Internal-API-Key).

Используется ботом для обогащения локального users_cache данными
пользователя (роль, имя, студия, активность) по user_id.

ВАЖНО про vk_id: текущая ручка auth GET /users/{id} (UserProfile) НЕ
содержит vk_id. Поэтому связку user_id <-> vk_id бот узнаёт не отсюда,
а из входящего сообщения Long Poll (from_id = доверенный vk_id) - что
естественно совпадает с ограничением VK (писать пользователю можно лишь
после того, как он сам начал диалог). Этот клиент даёт остальные поля
пользователя; vk_id он не возвращает, и код на него не рассчитывает.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class AuthClient:
    """Клиент межсервисных вызовов к Auth Service."""

    def __init__(self) -> None:
        self._base_url = settings.auth_service_url.rstrip("/")
        self._timeout = settings.external_service_timeout
        self._headers = {"X-Internal-API-Key": settings.internal_api_key}

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить профиль пользователя по id.

        Returns:
            dict с полями UserProfile (id, email, first_name, last_name,
            role, studio_id, is_active, ...) или None, если не найден (404).

        Raises:
            ExternalServiceError: транспортная ошибка или не-404 HTTP-ошибка.
        """
        url = f"{self._base_url}/api/v1/users/{user_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ExternalServiceError("auth", f"request failed: {exc}") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise ExternalServiceError(
                "auth", resp.text, status_code=resp.status_code
            )
        return resp.json()

    async def internal_vk_login(self, vk_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить токены платформы по доверенному vk_id (internal vk-login).

        Вызывает аддитивную internal-ручку auth (см. INTEGRATION_NOTES.md):
            POST /api/v1/auth/internal/vk-login  (X-Internal-API-Key)
            body: {"vk_id": <id>}
        Ручка переиспользует существующий auth_service.vk_login(vk_id),
        который по vk_id находит пользователя и выдаёт пару токенов.

        Returns:
            dict с полями user и tokens (как AuthResponse) при успехе;
            None, если по vk_id не найден пользователь (404 - человек
            написал боту, но не привязал VK к аккаунту на платформе).

        Raises:
            ExternalServiceError: транспорт/не-404 HTTP-ошибка.
        """
        url = f"{self._base_url}/api/v1/auth/internal/vk-login"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json={"vk_id": str(vk_id)}, headers=self._headers
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("auth", f"request failed: {exc}") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise ExternalServiceError(
                "auth", resp.text, status_code=resp.status_code
            )
        return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Обновить access-токен по refresh-токену.

        Использует существующий POST /api/v1/auth/refresh, который умеет
        брать refresh из тела запроса (для не-браузерных клиентов).

        Returns:
            новый access_token или None, если refresh недействителен
            (401 - токен протух/отозван, нужен повторный vk-login).
        """
        url = f"{self._base_url}/api/v1/auth/refresh"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json={"refresh_token": refresh_token}
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("auth", f"request failed: {exc}") from exc

        if resp.status_code == 401:
            return None
        if resp.status_code >= 400:
            raise ExternalServiceError(
                "auth", resp.text, status_code=resp.status_code
            )
        return resp.json().get("access_token")


auth_client = AuthClient()
