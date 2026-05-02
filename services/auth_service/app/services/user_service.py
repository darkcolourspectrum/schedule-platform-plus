from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.repositories.user_repository import UserRepository
from app.repositories.role_repository import RoleRepository
from app.core.exceptions import UserNotFoundException
from app.schemas.user import UserUpdate, UserListItem
from app.models.user import User
from app.messaging.outbox import (
    record_user_updated,
    record_user_deactivated,
    record_role_changed,
)
from app.services.redis_blacklist_service import RedisBlacklistService

logger = logging.getLogger(__name__)


class UserService:
    """Сервис для работы с пользователями"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.role_repo = RoleRepository(db)
        self.redis_blacklist = RedisBlacklistService(db)

    async def get_user_by_id(self, user_id: int) -> User:
        """Получение пользователя по ID"""
        
        user = await self.user_repo.get_by_id(
            user_id, 
            relationships=["role"]
        )
        
        if not user:
            raise UserNotFoundException()
        
        logger.info(f"Загружен пользователь {user_id}: bio='{user.bio}', first_name='{user.first_name}'")
        
        return user
    
    async def get_users_list(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
        studio_id: Optional[int] = None
    ) -> List[UserListItem]:
        """Получение списка пользователей с фильтрами"""
        
        filters = {}
        if studio_id:
            filters["studio_id"] = studio_id
        
        users = await self.user_repo.get_all(
            limit=limit,
            offset=offset,
            relationships=["role"],
            **filters
        )
        
        if role:
            users = [user for user in users if user.role.name == role]
        
        return [
            UserListItem(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role.name,
                studio_name=None,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login
            )
            for user in users
        ]
    
    async def update_user_profile(
        self,
        user_id: int,
        update_data: UserUpdate
    ) -> User:
        """Обновление профиля пользователя"""
        
        try:
            logger.info(f"Начало обновления профиля пользователя {user_id}")
            update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
            
            if not update_dict:
                logger.info(f"Нет данных для обновления пользователя {user_id}")
                user = await self.user_repo.get_by_id(user_id, relationships=["role"])
                if not user:
                    raise UserNotFoundException()
                return user
            
            try:
                logger.info(f"Обновление пользователя {user_id} с данными: {update_dict}")
                updated_user = await self.user_repo.update(user_id, **update_dict)
                
                if not updated_user:
                    raise UserNotFoundException()
                
                # Загружаем обновлённого пользователя с relationships для outbox
                user = await self.user_repo.get_by_id(user_id, relationships=["role"])
                
                # Запись события user.updated в outbox
                await record_user_updated(self.db, user, role_name=user.role.name)
                
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise
            
            logger.info(f"Пользователь {user_id} успешно обновлен")
            return user
            
        except UserNotFoundException:
            raise
        except Exception as e:
            logger.error(f"Ошибка обновления профиля пользователя {user_id}: {e}", exc_info=True)
            raise
    
    async def change_user_role(
        self,
        user_id: int,
        new_role_id: int,
        changed_by_user_id: Optional[int] = None
    ) -> User:
        """
        Изменение роли пользователя.
        
        Публикует отдельное событие role.changed (security-relevant), 
        с указанием старой и новой роли для аудита.
        """
        # Получаем текущего пользователя со старой ролью
        current_user = await self.user_repo.get_by_id(user_id, relationships=["role"])
        if not current_user:
            raise UserNotFoundException()
        
        old_role_id = current_user.role_id
        old_role_name = current_user.role.name
        
        # Получаем новую роль для имени
        new_role = await self.role_repo.get_by_id(new_role_id)
        if not new_role:
            raise ValueError(f"Role with id {new_role_id} not found")
        
        try:
            updated_user = await self.user_repo.update(user_id, role_id=new_role_id)
            if not updated_user:
                raise UserNotFoundException()
            
            await record_role_changed(
                self.db,
                user_id=user_id,
                old_role_id=old_role_id,
                old_role_name=old_role_name,
                new_role_id=new_role_id,
                new_role_name=new_role.name,
                changed_by_user_id=changed_by_user_id,
            )
            
            await self.db.commit()
            # User-level отзыв всех access-токенов: смена роли = критичное событие безопасности
            await self.redis_blacklist.revoke_all_user_tokens(user_id)
        except Exception:
            await self.db.rollback()
            raise
        
        # Возвращаем с обновлённым relationship
        return await self.user_repo.get_by_id(user_id, relationships=["role"])
    
    async def assign_user_to_studio(self, user_id: int, studio_id: int) -> User:
        """Привязка пользователя к студии"""
        try:
            updated_user = await self.user_repo.update(user_id, studio_id=studio_id)
            if not updated_user:
                raise UserNotFoundException()
            
            user = await self.user_repo.get_by_id(user_id, relationships=["role"])
            await record_user_updated(self.db, user, role_name=user.role.name)
            
            await self.db.commit()
            # User-level отзыв всех access-токенов: смена роли = критичное событие безопасности
            await self.redis_blacklist.revoke_all_user_tokens(user_id)
        except Exception:
            await self.db.rollback()
            raise
        
        return user
    
    async def activate_user(self, user_id: int) -> User:
        """Активация пользователя"""
        try:
            updated_user = await self.user_repo.update(user_id, is_active=True)
            if not updated_user:
                raise UserNotFoundException()
            
            user = await self.user_repo.get_by_id(user_id, relationships=["role"])
            await record_user_updated(self.db, user, role_name=user.role.name)
            
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        
        return user
    
    async def deactivate_user(self, user_id: int) -> User:
        """Деактивация пользователя"""
        try:
            updated_user = await self.user_repo.update(user_id, is_active=False)
            if not updated_user:
                raise UserNotFoundException()
            
            await record_user_deactivated(
                self.db,
                user_id=user_id,
                reason="admin_action"
            )
            
            await self.db.commit()
            # User-level отзыв всех access-токенов: смена роли = критичное событие безопасности
            await self.redis_blacklist.revoke_all_user_tokens(user_id)
        except Exception:
            await self.db.rollback()
            raise
        
        return await self.user_repo.get_by_id(user_id, relationships=["role"])