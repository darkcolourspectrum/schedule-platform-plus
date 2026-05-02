"""
FastAPI Dependencies для Schedule Service
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_schedule_db
from app.repositories.recurring_pattern_repository import RecurringPatternRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.user_repository import UserRepository
from app.services.lesson_generator_service import LessonGeneratorService
from app.services.recurring_pattern_service import RecurringPatternService
from app.services.lesson_service import LessonService
from app.services.schedule_service import ScheduleService
from app.core.security import extract_role_name, verify_internal_api_key
from app.config import settings

security = HTTPBearer(auto_error=False)


# ========== DATABASE DEPENDENCIES ==========

async def get_db() -> AsyncSession:
    """Get Schedule Service database session"""
    async for session in get_schedule_db():
        yield session


# ========== REPOSITORY DEPENDENCIES ==========

async def get_pattern_repository(
    db: AsyncSession = Depends(get_db)
) -> RecurringPatternRepository:
    """Get RecurringPatternRepository"""
    return RecurringPatternRepository(db)


async def get_lesson_repository(
    db: AsyncSession = Depends(get_db)
) -> LessonRepository:
    """Get LessonRepository"""
    return LessonRepository(db)


async def get_user_repository(
    db: AsyncSession = Depends(get_db)
) -> UserRepository:
    """Get UserRepository (читает из локального users_cache)"""
    return UserRepository(db)


# ========== SERVICE DEPENDENCIES ==========

async def get_generator_service(
    pattern_repo: RecurringPatternRepository = Depends(get_pattern_repository),
    lesson_repo: LessonRepository = Depends(get_lesson_repository)
) -> LessonGeneratorService:
    """Get LessonGeneratorService"""
    return LessonGeneratorService(pattern_repo, lesson_repo)


async def get_pattern_service(
    pattern_repo: RecurringPatternRepository = Depends(get_pattern_repository),
    lesson_repo: LessonRepository = Depends(get_lesson_repository),
    generator_service: LessonGeneratorService = Depends(get_generator_service)
) -> RecurringPatternService:
    """Get RecurringPatternService"""
    return RecurringPatternService(pattern_repo, lesson_repo, generator_service)


async def get_lesson_service(
    lesson_repo: LessonRepository = Depends(get_lesson_repository)
) -> LessonService:
    """Get LessonService"""
    return LessonService(lesson_repo)


async def get_schedule_service(
    lesson_repo: LessonRepository = Depends(get_lesson_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    generator_service: LessonGeneratorService = Depends(get_generator_service)
) -> ScheduleService:
    """Get ScheduleService"""
    return ScheduleService(lesson_repo, user_repo, generator_service)


# ========== AUTH DEPENDENCIES ==========

import redis.asyncio as redis_lib
from shared.auth_lib import (
    JWTValidator,
    BlacklistChecker,
    TokenPayload,
    InvalidTokenError,
    TokenTypeMismatchError,
)

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
    """Получить текущего пользователя из JWT токена с проверкой blacklist."""
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
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Проверить что пользователь - админ"""
    role = extract_role_name(current_user.get("role"))
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_teacher(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Проверить что пользователь - преподаватель (или админ)"""
    role = extract_role_name(current_user.get("role"))
    if role not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher or admin access required"
        )
    return current_user


async def verify_internal_key(
    x_internal_api_key: Optional[str] = Header(None)
) -> bool:
    """Проверка Internal API Key для межсервисного взаимодействия"""
    if not verify_internal_api_key(x_internal_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key"
        )
    return True


# ========== PERMISSION HELPERS ==========

def check_studio_access(user: dict, studio_id: int) -> bool:
    """
    Проверить имеет ли пользователь доступ к студии
    
    Args:
        user: Payload текущего пользователя
        studio_id: ID студии
        
    Returns:
        True если есть доступ
    """
    role = extract_role_name(user.get("role"))
    
    # Админ имеет доступ ко всем студиям
    if role == "admin":
        return True
    
    # Преподаватель/ученик имеет доступ только к своей студии
    user_studio_id = user.get("studio_id")
    return user_studio_id == studio_id


def check_teacher_access(user: dict, teacher_id: int) -> bool:
    """
    Проверить имеет ли пользователь доступ к данным преподавателя
    
    Args:
        user: Payload текущего пользователя
        teacher_id: ID преподавателя
        
    Returns:
        True если есть доступ
    """
    role = extract_role_name(user.get("role"))
    user_id = user.get("user_id")
    
    # Админ имеет доступ ко всем
    if role == "admin":
        return True
    
    # Преподаватель имеет доступ к своим данным
    if role == "teacher" and user_id == teacher_id:
        return True
    
    return False


def check_student_access(user: dict, student_id: int) -> bool:
    """
    Проверить имеет ли пользователь доступ к данным ученика
    
    Args:
        user: Payload текущего пользователя
        student_id: ID ученика
        
    Returns:
        True если есть доступ
    """
    role = extract_role_name(user.get("role"))
    user_id = user.get("user_id")
    
    # Админ и преподаватель имеют доступ ко всем ученикам своей студии
    if role in ["admin", "teacher"]:
        return True
    
    # Ученик имеет доступ только к своим данным
    if role == "student" and user_id == student_id:
        return True
    
    return False
