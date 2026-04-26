"""FastAPI dependencies for Notification Service"""
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
from app.services.notification_service import NotificationService


security = HTTPBearer(auto_error=False)


# ========== AUTH ==========

_jwt_validator: Optional[JWTValidator] = None
_blacklist_checker: Optional[BlacklistChecker] = None
_redis_client: Optional[redis_lib.Redis] = None


def get_jwt_validator() -> JWTValidator:
    global _jwt_validator
    if _jwt_validator is None:
        _jwt_validator = JWTValidator(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
    return _jwt_validator


async def get_blacklist_checker() -> BlacklistChecker:
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


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    validator: JWTValidator = Depends(get_jwt_validator),
    blacklist: BlacklistChecker = Depends(get_blacklist_checker),
) -> dict:
    """Получить текущего пользователя из JWT с проверкой blacklist."""
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


# ========== SERVICE ==========

async def get_notification_service(
    db: AsyncSession = Depends(get_db),
) -> NotificationService:
    return NotificationService(db)