"""
FastAPI-зависимости CRM Service.

Содержит:
    - провайдер LeadService;
    - JWT-аутентификацию (валидация токена + проверка blacklist);
    - проверку роли админа для защищённых эндпоинтов.

Auth-слой повторяет паттерн остальных сервисов (notification/admin):
JWTValidator и BlacklistChecker - синглтоны из shared/auth_lib.
"""

from typing import Optional

import redis.asyncio as redis_lib
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth_lib import (
    JWTValidator,
    BlacklistChecker,
    TokenPayload,
    InvalidTokenError,
    TokenTypeMismatchError,
)

from app.config import settings
from app.database.connection import get_db
from app.services.lead_service import LeadService


security = HTTPBearer(auto_error=False)


# ==================== SERVICE ====================


def get_lead_service(db: AsyncSession = Depends(get_db)) -> LeadService:
    """Провайдер LeadService с сессией БД."""
    return LeadService(db)


# ==================== AUTH ====================

# Синглтоны: создаются один раз при первом обращении и переиспользуются.
_jwt_validator: Optional[JWTValidator] = None
_blacklist_checker: Optional[BlacklistChecker] = None
_redis_client: Optional[redis_lib.Redis] = None


def get_jwt_validator() -> JWTValidator:
    """Получить singleton-валидатор JWT."""
    global _jwt_validator
    if _jwt_validator is None:
        _jwt_validator = JWTValidator(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
    return _jwt_validator


async def get_blacklist_checker() -> BlacklistChecker:
    """Получить singleton-проверщик blacklist отозванных токенов."""
    global _blacklist_checker, _redis_client
    if _blacklist_checker is None:
        _redis_client = redis_lib.from_url(
            settings.jwt_blacklist_redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        _blacklist_checker = BlacklistChecker(
            redis_client=_redis_client,
            fail_open=True,
        )
    return _blacklist_checker


def extract_role_name(role_data) -> str:
    """
    Извлечь имя роли из payload токена.

    Роль в JWT может прийти как строка ("admin") или как dict
    ({"name": "admin", ...}) - в разных частях системы исторически
    оба формата. Эта функция приводит к строке независимо от формата.
    """
    if role_data is None:
        return ""
    if isinstance(role_data, str):
        return role_data
    if isinstance(role_data, dict):
        return role_data.get("name", "")
    return str(role_data)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    validator: JWTValidator = Depends(get_jwt_validator),
    blacklist: BlacklistChecker = Depends(get_blacklist_checker),
) -> dict:
    """
    Получить текущего пользователя из JWT-токена.

    Проверяет подпись и срок токена, затем сверяется с blacklist
    (отозванные токены). Возвращает payload токена как dict.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload: TokenPayload = validator.decode(credentials.credentials)
    except (InvalidTokenError, TokenTypeMismatchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    if await blacklist.is_revoked(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    return payload.model_dump()


async def get_current_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Проверить, что текущий пользователь - админ.

    Вся работа с лидами доступна только роли admin: CRM-воронку ведут
    администраторы. Преподаватели и ученики доступа к лидам не имеют.
    """
    role = extract_role_name(current_user.get("role"))
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user