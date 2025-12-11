"""User Management Service - ПРОСТАЯ ВЕРСИЯ"""
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.connection import AuthAsyncSessionLocal, AdminAsyncSessionLocal
from app.models.auth_models import User, Role
from app.models.studio import Studio  # ← ИСПРАВЛЕН ИМПОРТ


class UserManagementService:
    """Сервис управления пользователями через Auth DB"""
    
    async def get_users_list(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
        studio_id: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> List[dict]:
        """Получить список пользователей"""
        async with AuthAsyncSessionLocal() as session:
            # Загружаем пользователей с ролями
            stmt = select(User).options(joinedload(User.role))
            
            if role:
                stmt = stmt.join(Role).where(Role.name == role)
            if studio_id:
                stmt = stmt.where(User.studio_id == studio_id)
            if is_active is not None:
                stmt = stmt.where(User.is_active == is_active)
            
            stmt = stmt.limit(limit).offset(offset)
            result = await session.execute(stmt)
            users = result.unique().scalars().all()
        
        # Получаем studio_names одним запросом
        studio_ids = [u.studio_id for u in users if u.studio_id]
        studio_map = {}
        if studio_ids:
            async with AdminAsyncSessionLocal() as admin_session:
                studios_result = await admin_session.execute(
                    select(Studio.id, Studio.name).where(Studio.id.in_(studio_ids))
                )
                studio_map = dict(studios_result.all())
        
        # Формируем ответ
        return [self._user_to_dict(u, studio_map.get(u.studio_id)) for u in users]
    
    async def update_user_role(self, user_id: int, role: str) -> dict:
        """Изменить роль пользователя"""
        role_id = self._get_role_id(role)
        
        async with AuthAsyncSessionLocal() as session:
            user = await session.get(User, user_id, options=[joinedload(User.role)])
            if not user:
                raise ValueError("User not found")
            
            user.role_id = role_id
            await session.commit()
            await session.refresh(user, ["role"])
            
            studio_name = await self._get_studio_name(user.studio_id) if user.studio_id else None
            return self._user_to_dict(user, studio_name)
    
    async def assign_user_to_studio(self, user_id: int, studio_id: int) -> dict:
        """Привязать пользователя к студии"""
        async with AuthAsyncSessionLocal() as session:
            user = await session.get(User, user_id, options=[joinedload(User.role)])
            if not user:
                raise ValueError("User not found")
            
            user.studio_id = studio_id
            await session.commit()
            
            studio_name = await self._get_studio_name(studio_id)
            return self._user_to_dict(user, studio_name)
    
    async def activate_user(self, user_id: int) -> dict:
        """Активировать пользователя"""
        async with AuthAsyncSessionLocal() as session:
            user = await session.get(User, user_id, options=[joinedload(User.role)])
            if not user:
                raise ValueError("User not found")
            
            user.is_active = True
            await session.commit()
            
            studio_name = await self._get_studio_name(user.studio_id) if user.studio_id else None
            return self._user_to_dict(user, studio_name)
    
    async def deactivate_user(self, user_id: int) -> dict:
        """Деактивировать пользователя"""
        async with AuthAsyncSessionLocal() as session:
            user = await session.get(User, user_id, options=[joinedload(User.role)])
            if not user:
                raise ValueError("User not found")
            
            user.is_active = False
            await session.commit()
            
            studio_name = await self._get_studio_name(user.studio_id) if user.studio_id else None
            return self._user_to_dict(user, studio_name)
    
    async def _get_studio_name(self, studio_id: int) -> Optional[str]:
        """Получить название студии по ID"""
        async with AdminAsyncSessionLocal() as session:
            result = await session.execute(
                select(Studio.name).where(Studio.id == studio_id)
            )
            return result.scalar_one_or_none()
    
    def _user_to_dict(self, user: User, studio_name: Optional[str] = None) -> dict:
        """Конвертация User в dict с полными данными"""
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name} {user.last_name}",
            "phone": user.phone,
            "role_id": user.role_id,
            "role": user.role.name if user.role else "guest",
            "studio_id": user.studio_id,
            "studio_name": studio_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "login_attempts": 0,
            "locked_until": None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "privacy_policy_accepted": user.privacy_policy_accepted,
            "privacy_policy_accepted_at": user.privacy_policy_accepted_at.isoformat() if user.privacy_policy_accepted_at else None,
        }
    
    def _get_role_id(self, role_name: str) -> int:
        """Получить ID роли по имени"""
        role_map = {"admin": 1, "teacher": 2, "student": 3, "guest": 4}
        return role_map.get(role_name.lower(), 3)