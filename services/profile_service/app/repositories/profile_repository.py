"""
Репозиторий для работы с профилями пользователей
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from sqlalchemy.exc import SQLAlchemyError
import logging

from app.models.profile import UserProfile
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ProfileRepository(BaseRepository[UserProfile]):
    """Репозиторий для работы с профилями пользователей"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(UserProfile, db)
    
    async def get_by_user_id(self, user_id: int) -> Optional[UserProfile]:
        """
        Получение профиля по ID пользователя
        
        Args:
            user_id: ID пользователя из Auth Service
            
        Returns:
            Профиль пользователя или None
        """
        try:
            result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            
            if profile:
                logger.debug(f"Найден профиль для пользователя {user_id}")
            else:
                logger.debug(f"Профиль для пользователя {user_id} не найден")
            
            return profile
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения профиля пользователя {user_id}: {e}")
            return None
    
    async def create_profile(
        self, 
        user_id: int,
        display_name: Optional[str] = None,
        bio: Optional[str] = None,
        phone: Optional[str] = None,
        **kwargs
    ) -> Optional[UserProfile]:
        """
        Создание нового профиля пользователя
        
        Args:
            user_id: ID пользователя из Auth Service
            display_name: Отображаемое имя
            bio: Биография
            phone: Телефон
            **kwargs: Дополнительные параметры
            
        Returns:
            Созданный профиль или None
        """
        try:
            # Проверяем, что профиль еще не существует
            existing_profile = await self.get_by_user_id(user_id)
            if existing_profile:
                logger.warning(f"Профиль для пользователя {user_id} уже существует")
                return existing_profile
            
            profile_data = {
                "user_id": user_id,
                "display_name": display_name,
                "bio": bio,
                "phone": phone,
                **kwargs
            }
            
            profile = await self.create(**profile_data)
            
            if profile:
                logger.info(f"Создан профиль для пользователя {user_id}")
            
            return profile
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка создания профиля для пользователя {user_id}: {e}")
            return None
    
    async def update_profile(
        self, 
        user_id: int, 
        **kwargs
    ) -> Optional[UserProfile]:
        """
        Обновление профиля пользователя
        
        Args:
            user_id: ID пользователя
            **kwargs: Данные для обновления
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.get_by_user_id(user_id)
            if not profile:
                logger.warning(f"Профиль пользователя {user_id} не найден для обновления")
                return None
            
            # Обновляем поля
            for key, value in kwargs.items():
                if hasattr(profile, key) and key not in ['id', 'user_id']:
                    setattr(profile, key, value)
            
            await self.db.commit()
            await self.db.refresh(profile)
            
            logger.debug(f"Обновлен профиль пользователя {user_id}")
            return profile
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления профиля пользователя {user_id}: {e}")
            return None
    
    async def update_avatar(self, user_id: int, avatar_filename: str) -> Optional[UserProfile]:
        """
        Обновление аватара пользователя
        
        Args:
            user_id: ID пользователя
            avatar_filename: Имя файла аватара
            
        Returns:
            Обновленный профиль или None
        """
        return await self.update_profile(user_id, avatar_filename=avatar_filename)
    
    async def update_notification_preferences(
        self, 
        user_id: int, 
        preferences: Dict[str, bool]
    ) -> Optional[UserProfile]:
        """
        Обновление настроек уведомлений
        
        Args:
            user_id: ID пользователя
            preferences: Словарь с настройками уведомлений
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.get_by_user_id(user_id)
            if not profile:
                logger.warning(f"Профиль пользователя {user_id} не найден для обновления уведомлений")
                return None
            
            # Обновляем настройки уведомлений
            current_preferences = profile.notification_preferences or {}
            current_preferences.update(preferences)
            profile.notification_preferences = current_preferences
            
            await self.db.commit()
            await self.db.refresh(profile)
            
            logger.debug(f"Обновлены настройки уведомлений пользователя {user_id}")
            return profile
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления настроек уведомлений пользователя {user_id}: {e}")
            return None
    
    async def update_profile_settings(
        self, 
        user_id: int, 
        settings: Dict[str, Any]
    ) -> Optional[UserProfile]:
        """
        Обновление настроек профиля
        
        Args:
            user_id: ID пользователя
            settings: Словарь с настройками профиля
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.get_by_user_id(user_id)
            if not profile:
                logger.warning(f"Профиль пользователя {user_id} не найден для обновления настроек")
                return None
            
            # Обновляем настройки профиля
            current_settings = profile.profile_settings or {}
            current_settings.update(settings)
            profile.profile_settings = current_settings
            
            await self.db.commit()
            await self.db.refresh(profile)
            
            logger.debug(f"Обновлены настройки профиля пользователя {user_id}")
            return profile
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления настроек профиля пользователя {user_id}: {e}")
            return None
    
    async def increment_profile_views(self, user_id: int) -> Optional[UserProfile]:
        """
        Увеличение счетчика просмотров профиля
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.get_by_user_id(user_id)
            if not profile:
                logger.warning(f"Профиль пользователя {user_id} не найден для увеличения просмотров")
                return None
            
            profile.increment_views()
            
            await self.db.commit()
            await self.db.refresh(profile)
            
            logger.debug(f"Увеличен счетчик просмотров профиля пользователя {user_id}")
            return profile
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка увеличения просмотров профиля пользователя {user_id}: {e}")
            return None
    
    async def update_last_activity(self, user_id: int) -> Optional[UserProfile]:
        """
        Обновление времени последней активности
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.get_by_user_id(user_id)
            if not profile:
                logger.warning(f"Профиль пользователя {user_id} не найден для обновления активности")
                return None
            
            profile.update_last_activity()
            
            await self.db.commit()
            await self.db.refresh(profile)
            
            logger.debug(f"Обновлено время последней активности пользователя {user_id}")
            return profile
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления активности пользователя {user_id}: {e}")
            return None
    
    async def get_public_profiles(
        self, 
        limit: int = 20,
        offset: int = 0
    ) -> List[UserProfile]:
        """
        Получение публичных профилей
        
        Args:
            limit: Максимальное количество профилей
            offset: Смещение для пагинации
            
        Returns:
            Список публичных профилей
        """
        try:
            result = await self.db.execute(
                select(UserProfile)
                .where(UserProfile.is_profile_public == True)
                .order_by(desc(UserProfile.profile_views))
                .limit(limit)
                .offset(offset)
            )
            profiles = result.scalars().all()
            
            logger.debug(f"Получено {len(profiles)} публичных профилей")
            return list(profiles)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения публичных профилей: {e}")
            return []
    
    async def search_profiles(
        self, 
        query: str,
        limit: int = 20
    ) -> List[UserProfile]:
        """
        Поиск профилей по имени или биографии
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных профилей
        """
        try:
            search_pattern = f"%{query.lower()}%"
            
            result = await self.db.execute(
                select(UserProfile)
                .where(
                    and_(
                        UserProfile.is_profile_public == True,
                        func.lower(UserProfile.display_name).like(search_pattern) |
                        func.lower(UserProfile.bio).like(search_pattern)
                    )
                )
                .order_by(desc(UserProfile.profile_views))
                .limit(limit)
            )
            profiles = result.scalars().all()
            
            logger.debug(f"Найдено {len(profiles)} профилей по запросу '{query}'")
            return list(profiles)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка поиска профилей по запросу '{query}': {e}")
            return []
    
    async def get_profiles_by_user_ids(self, user_ids: List[int]) -> List[UserProfile]:
        """
        Получение профилей по списку ID пользователей
        
        Args:
            user_ids: Список ID пользователей
            
        Returns:
            Список профилей
        """
        try:
            if not user_ids:
                return []
            
            result = await self.db.execute(
                select(UserProfile)
                .where(UserProfile.user_id.in_(user_ids))
                .order_by(UserProfile.user_id)
            )
            profiles = result.scalars().all()
            
            logger.debug(f"Получено {len(profiles)} профилей для {len(user_ids)} пользователей")
            return list(profiles)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения профилей по списку ID: {e}")
            return []