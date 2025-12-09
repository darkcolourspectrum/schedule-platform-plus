"""FastAPI Dependencies"""
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_admin_db
from app.services.studio_service import StudioService
from app.services.classroom_service import ClassroomService
from app.services.user_cache_service import user_cache_service
from app.core.auth import decode_jwt_token
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

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """Get current user from JWT token"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    payload = decode_jwt_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    return payload

async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Verify user is admin"""
    role = current_user.get("role")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

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

# User Management и Dashboard dependencies
from app.services.user_management_service import UserManagementService
from app.services.dashboard_service import DashboardService


async def get_user_management_service() -> UserManagementService:
    """Get User Management Service"""
    return UserManagementService()


async def get_dashboard_service() -> DashboardService:
    """Get Dashboard Service"""
    return DashboardService()
