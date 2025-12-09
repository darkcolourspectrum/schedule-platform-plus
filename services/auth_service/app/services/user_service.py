from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.repositories.user_repository import UserRepository
from app.core.exceptions import UserNotFoundException
from app.schemas.user import UserUpdate, UserListItem
from app.models.user import User

logger = logging.getLogger(__name__)

class UserService:
    """Сервис для работы с пользователями"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
    
    async def get_user_by_id(self, user_id: int) -> User:
        """Получение пользователя по ID"""
        
        user = await self.user_repo.get_by_id(
            user_id, 
            relationships=["role"]  # УБРАЛ "studio"
        )
        
        if not user:
            raise UserNotFoundException()
        
        logger.info(f"Загружен пользователь {user_id}: bio='{user.bio}', first_name='{user.first_name}'")
        logger.info(f"Атрибуты объекта user: {[attr for attr in dir(user) if not attr.startswith('_')]}")

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
            relationships=["role"],  # УБРАЛ "studio"
            **filters
        )
        
        # Фильтрация по роли (если указана)
        if role:
            users = [user for user in users if user.role.name == role]
        
        return [
            UserListItem(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role.name,
                studio_name=None,  # Studio больше нет - всегда None
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
            logger.info(f"Данные для обновления: {update_data.dict(exclude_unset=True)}")
            
            # Получаем только не None значения
            update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
            
            if not update_dict:
                logger.info(f"Нет данных для обновления пользователя {user_id}, возвращаем существующего")
                user = await self.user_repo.get_by_id(user_id, relationships=["role"])
                if not user:
                    raise UserNotFoundException()
                return user
            
            logger.info(f"Обновление пользователя {user_id} с данными: {update_dict}")
            updated_user = await self.user_repo.update(user_id, **update_dict)
            
            if not updated_user:
                raise UserNotFoundException()
            
            # Загружаем обновленного пользователя с relationships
            user = await self.user_repo.get_by_id(user_id, relationships=["role"])
            
            logger.info(f"Пользователь {user_id} успешно обновлен")
            return user
            
        except UserNotFoundException:
            raise
        except Exception as e:
            logger.error(f"Ошибка обновления профиля пользователя {user_id}: {e}", exc_info=True)
            raise
    
    async def change_user_role(self, user_id: int, new_role_id: int) -> User:
        """Изменение роли пользователя"""
        updated_user = await self.user_repo.update(user_id, role_id=new_role_id)
        
        if not updated_user:
            raise UserNotFoundException()
        
        return updated_user
    
    async def assign_user_to_studio(self, user_id: int, studio_id: int) -> User:
        """Привязка пользователя к студии"""
        updated_user = await self.user_repo.update(user_id, studio_id=studio_id)
        
        if not updated_user:
            raise UserNotFoundException()
        
        return updated_user
    
    async def activate_user(self, user_id: int) -> User:
        """Активация пользователя"""
        updated_user = await self.user_repo.update(user_id, is_active=True)
        
        if not updated_user:
            raise UserNotFoundException()
        
        return updated_user
    
    async def deactivate_user(self, user_id: int) -> User:
        """Деактивация пользователя"""
        updated_user = await self.user_repo.update(user_id, is_active=False)
        
        if not updated_user:
            raise UserNotFoundException()
        
        return updated_user