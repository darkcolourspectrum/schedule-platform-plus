"""Users API Endpoints - читаем User данные через User Cache Service"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException

from app.schemas.user import UserResponse
from app.services.user_cache_service import UserCacheService
from app.dependencies import get_user_cache, get_current_admin

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/", response_model=List[UserResponse])
async def get_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    admin: dict = Depends(get_current_admin),
    user_cache: UserCacheService = Depends(get_user_cache)
):
    """Get all users (через User Cache)"""
    if role:
        users = await user_cache.get_users_by_role(role, is_active)
    else:
        # TODO: get all users
        users = []
    return users

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    admin: dict = Depends(get_current_admin),
    user_cache: UserCacheService = Depends(get_user_cache)
):
    """Get user by ID (через User Cache)"""
    user = await user_cache.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/role/{role_name}", response_model=List[UserResponse])
async def get_users_by_role(
    role_name: str,
    admin: dict = Depends(get_current_admin),
    user_cache: UserCacheService = Depends(get_user_cache)
):
    """Get users by role (через User Cache)"""
    users = await user_cache.get_users_by_role(role_name)
    return users
