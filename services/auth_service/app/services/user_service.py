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
            relationships=["role", "studio"]
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
            relationships=["role", "studio"],
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
                studio_name=user.studio.name if user.studio else None,
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
                # Если нет данных для обновления, возвращаем существующего пользователя
                return await self.get_user_by_id(user_id)
            
            logger.info(f"Обновляем пользователя {user_id} с данными: {update_dict}")
            
            # Получаем пользователя до обновления
            existing_user = await self.get_user_by_id(user_id)
            logger.info(f"Существующие данные пользователя {user_id}: bio='{existing_user.bio}'")
            
            updated_user = await self.user_repo.update(user_id, **update_dict)
            
            if not updated_user:
                logger.error(f"update() вернул None для пользователя {user_id}")
                raise UserNotFoundException()
            
            await self.db.close()

            # Загружаем обновленного пользователя со связями
            result_user = await self.get_user_by_id(user_id)
            logger.info(f"Результат обновления пользователя {user_id}: bio='{result_user.bio}'")
            
            logger.info(f"Профиль пользователя {user_id} успешно обновлен")
            return result_user
            
        except UserNotFoundException:
            logger.error(f"Пользователь {user_id} не найден")
            raise
        except Exception as e:
            logger.error(f"Ошибка при обновлении профиля пользователя {user_id}: {str(e)}")
            logger.exception("Детальная ошибка:")
            raise