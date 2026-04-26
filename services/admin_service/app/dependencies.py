"""FastAPI Dependencies"""
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_admin_db
from app.services.studio_service import StudioService
from app.services.classroom_service import ClassroomService
from app.services.user_cache_service import user_cache_service
from app.config import settings

security = HTTPBearer(auto_error=False)

# ========== DATABASE DEPENDENCIES ==========

async def get_db() -> AsyncSession:
    """Get database session"""
    async for session in get_admin_db():
        yield session

# ========== SERVICE DEPENDENCIES ==========

async def get_studio_service(db: AsyncSession = Depends(get_db)) -> StudioService:
    return StudioService(db)

async def get_classroom_service(db: AsyncSession = Depends(get_db)) -> ClassroomService:
    return ClassroomService(db)

def get_user_cache():
    return user_cache_service

# ========== AUTH DEPENDENCIES ==========

import redis.asyncio as redis_lib
from shared.auth_lib import (
    JWTValidator,
    BlacklistChecker,
    TokenPayload,
    InvalidTokenError,
    TokenTypeMismatchError,
)

# Singleton-инстансы (создаются один раз при первом обращении)
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
    """Получить singleton-проверщик blacklist."""
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
    """Get current user from JWT token (with blacklist check)."""
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


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Verify user is admin."""
    role = current_user.get("role")
    role_name = role.get("name") if isinstance(role, dict) else str(role) if role else ""
    if role_name != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user

# ========== USER MANAGEMENT & DASHBOARD ==========

from app.services.user_management_service import UserManagementService
from app.services.dashboard_service import DashboardService


async def get_user_management_service() -> UserManagementService:
    """Get User Management Service"""
    return UserManagementService()


async def get_dashboard_service() -> DashboardService:
    """Get Dashboard Service"""
    return DashboardService()


# ========== INTERNAL API KEY ==========

async def verify_internal_api_key(
    x_internal_api_key: Optional[str] = Header(None)
) -> bool:
    """Verify internal API key for service-to-service communication"""
    if not x_internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal API key required"
        )
    
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key"
        )
    
    return True