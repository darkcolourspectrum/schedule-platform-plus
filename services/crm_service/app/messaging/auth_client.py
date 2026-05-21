"""
HTTP-клиент для общения CRM Service с Auth Service.

Используется при конвертации лида в клиента: CRM просит Auth Service
создать provisioned-пользователя (аккаунт без пароля). Это единственная
синхронная межсервисная связь CRM - она нужна, потому что CRM должен
немедленно получить id созданного пользователя, чтобы записать его в лид
(converted_user_id) и вернуть фронту для создания первого занятия.

Auth Service в ответ публикует событие user.created в свой outbox, которое
позже придёт в CRM через consumer и наполнит users_cache. То есть данные
пользователя приходят двумя путями: id - синхронно (сразу), полная карточка
в кеш - асинхронно (событием). Это нормально и не требует синхронизации.

Аутентификация между сервисами - через X-Internal-API-Key.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AuthServiceError(Exception):
    """Базовая ошибка при обращении к Auth Service."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AuthServiceUserConflict(AuthServiceError):
    """
    Email уже занят в Auth Service (HTTP 409).

    Сценарий: лид оставил заявку с email, который уже зарегистрирован
    в системе. Конвертация в нового пользователя в этом случае невозможна.
    """


class AuthServiceClient:
    """HTTP-клиент к Auth Service для операций конвертации лида."""

    def __init__(self):
        self.base_url = settings.auth_service_url.rstrip("/")
        self.timeout = settings.auth_service_timeout
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-API-Key": settings.internal_api_key,
        }

    async def provision_user(
        self,
        email: str,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        studio_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Создать provisioned-пользователя в Auth Service.

        Вызывает внутренний эндпоинт POST /api/v1/users/provision.

        Returns:
            UserProfile созданного пользователя (dict с полями id, email,
            first_name, last_name, role, is_active, ...).

        Raises:
            AuthServiceUserConflict: email уже занят (HTTP 409).
            AuthServiceError: сетевая ошибка или иной неуспешный ответ.
        """
        url = f"{self.base_url}/api/v1/users/provision"
        body = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "studio_id": studio_id,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url, headers=self.headers, json=body
                )
        except httpx.RequestError as exc:
            logger.error("Auth Service network error on provision: %s", exc)
            raise AuthServiceError(
                f"Network error calling Auth Service: {exc}"
            ) from exc

        if response.status_code == 201:
            return response.json()

        if response.status_code == 409:
            logger.warning(
                "Auth Service: email already exists, provision rejected: %s",
                email,
            )
            raise AuthServiceUserConflict(
                f"User with email '{email}' already exists in Auth Service"
            )

        logger.error(
            "Auth Service provision error: status=%s body=%s",
            response.status_code, response.text,
        )
        raise AuthServiceError(
            f"Auth Service returned {response.status_code}: {response.text}",
            status_code=response.status_code,
        )


# Singleton-экземпляр клиента.
auth_client = AuthServiceClient()