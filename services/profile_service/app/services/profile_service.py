"""
Основной сервис для работы с профилями пользователей
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import UserProfile
from app.repositories.profile_repository import ProfileRepository
from app.services.auth_client import auth_client
from app.services.cache_service import cache_service
from app.config import settings

logger = logging.getLogger(__name__)

def extract_role_name(role_data) -> str:
    """
    Универсальная функция для извлечения имени роли
    Работает и со старым форматом (dict) и с новым (string)
    
    Args:
        role_data: Данные роли - может быть str, dict или None
        
    Returns:
        Имя роли как строка
    """
    if role_data is None:
        return "student"
    if isinstance(role_data, str):
        return role_data
    if isinstance(role_data, dict):
        return role_data.get("name", "student")
    return "student"

class ProfileService:
    """Сервис для работы с профилями пользователей"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.profile_repo = ProfileRepository(db)
    
    async def get_profile_by_user_id(
        self, 
        user_id: int,
        viewer_user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Получение полного профиля пользователя с данными из Auth Service
        
        Args:
            user_id: ID пользователя
            viewer_user_id: ID пользователя, который просматривает профиль
            
        Returns:
            Словарь с полными данными профиля или None
        """
        try:
            # Кэш используем только для просмотра ЧУЖИХ профилей.
            # Свой профиль читаем всегда из БД, чтобы пользователь сразу
            # видел собственные изменения (read-your-own-writes).
            is_own_profile = (viewer_user_id is not None and viewer_user_id == user_id)
            cache_key = f"profile_full:{user_id}"
            
            if not is_own_profile:
                cached_data = await cache_service.get(cache_key)
                if cached_data:
                    logger.debug(f"Профиль пользователя {user_id} получен из кэша")
                    
                    return cached_data
            
            # Получаем данные пользователя из Auth Service
            user_data = await auth_client.get_user_by_id(user_id)
            if not user_data:
                logger.warning(f"Пользователь {user_id} не найден в Auth Service")
                return None
            
            # Получаем профиль из нашей БД
            profile = await self.profile_repo.get_by_user_id(user_id)
            
            # Если профиля нет, создаем базовый
            if not profile:
                profile = await self._create_default_profile(user_id, user_data)
            
            # Собираем полные данные профиля
            full_profile = await self._build_full_profile(user_data, profile, viewer_user_id == user_id)
            
            # В кэш кладём только если это просмотр чужого профиля.
            if not is_own_profile:
                await cache_service.set(
                    cache_key, 
                    full_profile, 
                    ttl=settings.cache_user_profile_ttl
                )
            
            logger.debug(f"Собран полный профиль пользователя {user_id}")
            return full_profile
            
        except Exception as e:
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
            user_id: ID пользователя
            display_name: Отображаемое имя
            bio: Биография
            phone: Телефон
            **kwargs: Дополнительные параметры
            
        Returns:
            Созданный профиль или None
        """
        try:
            # Проверяем существование пользователя в Auth Service
            user_data = await auth_client.get_user_by_id(user_id)
            if not user_data:
                logger.warning(f"Пользователь {user_id} не найден в Auth Service")
                return None
            
            # Создаем профиль
            profile = await self.profile_repo.create_profile(
                user_id=user_id,
                display_name=display_name or user_data.get("first_name", ""),
                bio=bio,
                phone=phone,
                **kwargs
            )
            
            if profile:
                # Очищаем кэш
                await self._clear_profile_cache(user_id)
                
                logger.info(f"Создан профиль для пользователя {user_id}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Ошибка создания профиля пользователя {user_id}: {e}")
            return None
    
    async def update_profile(
        self,
        user_id: int,
        **update_data
    ) -> Optional[UserProfile]:
        """
        Обновление профиля пользователя в Profile БД.
        
        Profile владеет: display_name, bio, avatar_filename, phone(?), 
        date_of_birth, is_profile_public, show_contact_info, 
        notification_preferences, profile_settings.
        
        Базовые поля (first_name, last_name, role, email) принадлежат Auth -
        фронт должен слать их в Auth напрямую.
        """
        try:
            # Защита: отбрасываем поля которые принадлежат Auth.
            auth_only_fields = {'first_name', 'last_name'}
            stray = set(update_data.keys()) & auth_only_fields
            if stray:
                logger.warning(
                    f"Profile.update_profile получил Auth-поля {stray}, игнорируем. "
                    f"Фронт должен отправлять их в Auth Service напрямую."
                )
                update_data = {
                    k: v for k, v in update_data.items()
                    if k not in auth_only_fields
                }
            
            if not update_data:
                logger.debug(f"Нет полей для обновления профиля {user_id}")
                return await self.profile_repo.get_by_user_id(user_id)
            
            profile = await self.profile_repo.update_profile(user_id, **update_data)
            
            if profile:
                await self._clear_profile_cache(user_id)
                logger.info(f"Обновлён профиль пользователя {user_id}: {list(update_data.keys())}")
            
            return profile
        
        except Exception as e:
            logger.error(f"Ошибка обновления профиля пользователя {user_id}: {e}")
            return None
    
    async def update_avatar(
        self,
        user_id: int,
        avatar_filename: str
    ) -> Optional[UserProfile]:
        """
        Обновление аватара пользователя
        
        Args:
            user_id: ID пользователя
            avatar_filename: Имя файла аватара
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.profile_repo.update_avatar(user_id, avatar_filename)
            
            if profile:
                # Очищаем кэш
                await self._clear_profile_cache(user_id)
                
                logger.info(f"Обновлен аватар пользователя {user_id}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Ошибка обновления аватара пользователя {user_id}: {e}")
            return None
    
    async def update_notification_preferences(
        self,
        user_id: int,
        preferences: Dict[str, bool]
    ) -> Optional[UserProfile]:
        """
        Обновление настроек уведомлений
        
        Args:
            user_id: ID пользователя
            preferences: Новые настройки уведомлений
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.profile_repo.update_notification_preferences(user_id, preferences)
            
            if profile:
                # Очищаем кэш
                await self._clear_profile_cache(user_id)
                
                logger.debug(f"Обновлены настройки уведомлений пользователя {user_id}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Ошибка обновления настроек уведомлений пользователя {user_id}: {e}")
            return None
    
    async def update_profile_settings(
        self,
        user_id: int,
        settings_data: Dict[str, Any]
    ) -> Optional[UserProfile]:
        """
        Обновление настроек профиля
        
        Args:
            user_id: ID пользователя
            settings_data: Новые настройки профиля
            
        Returns:
            Обновленный профиль или None
        """
        try:
            profile = await self.profile_repo.update_profile_settings(user_id, settings_data)
            
            if profile:
                # Очищаем кэш
                await self._clear_profile_cache(user_id)
                
                logger.debug(f"Обновлены настройки профиля пользователя {user_id}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Ошибка обновления настроек профиля пользователя {user_id}: {e}")
            return None
    
    async def search_profiles(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Поиск публичных профилей
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных профилей с базовой информацией
        """
        try:
            profiles = await self.profile_repo.search_profiles(query, limit)
            
            result = []
            for profile in profiles:
                # Получаем базовую информацию пользователя
                user_data = await auth_client.get_user_by_id(profile.user_id)
                if user_data:
                    profile_data = {
                        "user_id": profile.user_id,
                        "display_name": profile.display_name or user_data.get("first_name", ""),
                        "avatar_url": profile.avatar_url,
                        "bio": profile.bio,
                        "profile_views": profile.profile_views,
                        "role": extract_role_name(user_data.get("role")),
                        "is_verified": user_data.get("is_verified", False)
                    }
                    result.append(profile_data)
            
            logger.debug(f"Найдено {len(result)} профилей по запросу '{query}'")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка поиска профилей по запросу '{query}': {e}")
            return []
    
    async def get_public_profiles(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Получение списка публичных профилей
        
        Args:
            limit: Максимальное количество профилей
            offset: Смещение для пагинации
            
        Returns:
            Список публичных профилей
        """
        try:
            profiles = await self.profile_repo.get_public_profiles(limit, offset)
            
            result = []
            for profile in profiles:
                user_data = await auth_client.get_user_by_id(profile.user_id)
                if user_data:
                    profile_data = {
                        "user_id": profile.user_id,
                        "display_name": profile.display_name or user_data.get("first_name", ""),
                        "avatar_url": profile.avatar_url,
                        "bio": profile.bio,
                        "profile_views": profile.profile_views,
                        "role": extract_role_name(user_data.get("role")),
                        "is_verified": user_data.get("is_verified", False)
                    }
                    result.append(profile_data)
            
            logger.debug(f"Получено {len(result)} публичных профилей")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения публичных профилей: {e}")
            return []
    
    # Приватные методы
    
    async def _create_default_profile(
        self, 
        user_id: int, 
        user_data: Dict[str, Any]
    ) -> Optional[UserProfile]:
        """Создание профиля по умолчанию для нового пользователя"""
        try:
            display_name = user_data.get("first_name", "")
            if user_data.get("last_name"):
                display_name += f" {user_data['last_name']}"
            
            profile = await self.profile_repo.create_profile(
                user_id=user_id,
                display_name=display_name.strip() or None,
                is_profile_public=True  # По умолчанию профиль публичный
            )
            
            if profile:
                logger.info(f"Создан профиль по умолчанию для пользователя {user_id}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Ошибка создания профиля по умолчанию для пользователя {user_id}: {e}")
            return None
    
    async def _build_full_profile(
        self, 
        user_data: Dict[str, Any], 
        profile: UserProfile,
        is_owner: bool
    ) -> Dict[str, Any]:
        """Сборка полного профиля пользователя"""
        
        # Извлекаем role правильно
        role_name = extract_role_name(user_data.get("role"))
        
        # ИСПРАВЛЕНО: Формируем user_info отдельно для схемы
        user_info = {
            "id": user_data.get("id") or profile.user_id,
            "email": user_data.get("email"),
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "role": {"name": role_name},
            "is_verified": user_data.get("is_verified", False),
            "created_at": user_data.get("created_at"),
        }
        
        # Данные профиля
        profile_dict = profile.to_dict_private() if is_owner else profile.to_dict_public()
        
        # ВАЖНО: Возвращаем в формате который ожидает ProfileResponse
        full_profile = {
            "user_info": user_info,  # Вложенный объект
            **profile_dict  # Остальные поля профиля
        }
        
        return full_profile
    
    
    async def _clear_profile_cache(self, user_id: int):
        """Очистка кэша профиля пользователя"""
        try:
            cache_keys = [
                f"profile_full:{user_id}",
            ]
            
            for key in cache_keys:
                await cache_service.delete(key)
            
            logger.debug(f"Очищен кэш профиля пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки кэша профиля {user_id}: {e}")