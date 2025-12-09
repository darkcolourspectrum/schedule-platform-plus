"""User Management Service"""
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AuthAsyncSessionLocal
from app.models.auth_models import User
from app.schemas.user import UserResponse


class UserManagementService:
    """Сервис управления пользователями через Auth DB"""
    
    async def get_users_list(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
        studio_id: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> List[UserResponse]:
        """Получить список пользователей"""
        async with AuthAsyncSessionLocal() as session:
            stmt = select(User)
            
            if role:
                stmt = stmt.where(User.role_id == self._get_role_id(role))
            if studio_id:
                stmt = stmt.where(User.studio_id == studio_id)
            if is_active is not None:
                stmt = stmt.where(User.is_active == is_active)
            
            stmt = stmt.limit(limit).offset(offset)
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            return [UserResponse.from_orm(user) for user in users]
    
    async def update_user_role(self, user_id: int, role: str) -> UserResponse:
        """Изменить роль пользователя"""
        role_id = self._get_role_id(role)
        
        async with AuthAsyncSessionLocal() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(role_id=role_id)
                .returning(User)
            )
            result = await session.execute(stmt)
            await session.commit()
            user = result.scalar_one()
            return UserResponse.from_orm(user)
    
    async def assign_user_to_studio(self, user_id: int, studio_id: int) -> UserResponse:
        """Привязать пользователя к студии"""
        async with AuthAsyncSessionLocal() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(studio_id=studio_id)
                .returning(User)
            )
            result = await session.execute(stmt)
            await session.commit()
            user = result.scalar_one()
            return UserResponse.from_orm(user)
    
    async def activate_user(self, user_id: int) -> UserResponse:
        """Активировать пользователя"""
        async with AuthAsyncSessionLocal() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(is_active=True)
                .returning(User)
            )
            result = await session.execute(stmt)
            await session.commit()
            user = result.scalar_one()
            return UserResponse.from_orm(user)
    
    async def deactivate_user(self, user_id: int) -> UserResponse:
        """Деактивировать пользователя"""
        async with AuthAsyncSessionLocal() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(is_active=False)
                .returning(User)
            )
            result = await session.execute(stmt)
            await session.commit()
            user = result.scalar_one()
            return UserResponse.from_orm(user)
    
    def _get_role_id(self, role: str) -> int:
        """Получить ID роли по названию"""
        role_map = {"admin": 1, "teacher": 2, "student": 3}
        return role_map.get(role.lower(), 3)
