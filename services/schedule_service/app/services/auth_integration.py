"""
Сервис интеграции с Auth Service
Обеспечивает взаимодействие Schedule Service с сервисом аутентификации
"""

from typing import Optional, Dict, Any, List
import httpx
import logging

from app.config import settings
from app.core.exceptions import AuthServiceUnavailableException
from app.services.redis_cache_service import redis_cache_service

logger = logging.getLogger(__name__)


class AuthServiceIntegration:
    """
    Сервис для интеграции с Auth Service
    Предоставляет методы для получения данных пользователей и студий
    """
    
    def __init__(self):
        self.base_url = settings.auth_service_url
        self.timeout = settings.auth_service_timeout
        self.internal_api_key = settings.internal_api_key
    
    @property
    def headers(self) -> Dict[str, str]:
        """Заголовки для внутренних запросов к Auth Service"""
        return {
            "X-Internal-API-Key": self.internal_api_key,
            "Content-Type": "application/json"
        }
    
    async def validate_user_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Валидация access токена пользователя через Auth Service
        
        Args:
            access_token: JWT токен пользователя
            
        Returns:
            Dict с данными пользователя или None если токен недействителен
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/validate-token",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        **self.headers
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Token validation failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            raise AuthServiceUnavailableException()
    
    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение информации о пользователе по ID с Redis кэшированием
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Информация о пользователе или None
        """
        # Проверяем кэш
        cached_data = await redis_cache_service.get_cached_user(user_id)
        if cached_data:
            return cached_data
        
        # Запрос к Auth Service
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    # Кэшируем результат
                    await redis_cache_service.cache_user(user_id, user_data)
                    return user_data
                elif response.status_code == 404:
                    logger.warning(f"User {user_id} not found")
                    return None
                else:
                    logger.error(f"Failed to get user info: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            raise AuthServiceUnavailableException()
    
    async def get_studio_info(self, studio_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение информации о студии с Redis кэшированием
        
        Args:
            studio_id: ID студии
            
        Returns:
            Информация о студии или None
        """
        # Проверяем кэш
        cached_data = await redis_cache_service.get_cached_studio(studio_id)
        if cached_data:
            return cached_data
        
        # Запрос к Auth Service
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/studios/{studio_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    studio_data = response.json()
                    # Кэшируем результат
                    await redis_cache_service.cache_studio(studio_id, studio_data)
                    return studio_data
                elif response.status_code == 404:
                    logger.warning(f"Studio {studio_id} not found")
                    return None
                else:
                    logger.error(f"Failed to get studio info: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting studio info: {e}")
            raise AuthServiceUnavailableException()
    
    async def get_user_permissions(
        self,
        user_id: int,
        studio_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Получение прав пользователя с Redis кэшированием
        
        Args:
            user_id: ID пользователя
            studio_id: ID студии для проверки прав
            
        Returns:
            Права пользователя
        """
        # Проверяем кэш
        cached_data = await redis_cache_service.get_cached_permissions(user_id, studio_id)
        if cached_data:
            return cached_data
        
        # Запрос к Auth Service
        try:
            params = {}
            if studio_id:
                params["studio_id"] = studio_id
                
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/permissions",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    permissions_data = response.json()
                    # Кэшируем результат
                    await redis_cache_service.cache_permissions(user_id, permissions_data, studio_id)
                    return permissions_data
                else:
                    logger.error(f"Failed to get user permissions: {response.status_code}")
                    return {"permissions": [], "role": "guest"}
                    
        except Exception as e:
            logger.error(f"Error getting user permissions: {e}")
            return {"permissions": [], "role": "guest"}
    
    async def get_teachers_by_studio(self, studio_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка преподавателей студии с Redis кэшированием
        
        Args:
            studio_id: ID студии
            
        Returns:
            Список преподавателей
        """
        # Проверяем кэш
        cached_data = await redis_cache_service.get_cached_teachers(studio_id)
        if cached_data:
            return cached_data
        
        # Запрос к Auth Service
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/studios/{studio_id}/teachers",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    teachers_data = response.json()
                    # Кэшируем результат
                    await redis_cache_service.cache_teachers(studio_id, teachers_data)
                    return teachers_data
                else:
                    logger.error(f"Failed to get teachers: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting teachers: {e}")
            return []
    
    async def search_students(
        self,
        query: str,
        studio_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Поиск учеников для записи на урок
        
        Args:
            query: Поисковый запрос (имя, email)
            studio_id: Ограничение по студии
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных учеников
        """
        try:
            params = {
                "q": query,
                "role": "student",
                "limit": limit
            }
            
            if studio_id:
                params["studio_id"] = studio_id
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/search",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to search students: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error searching students: {e}")
            return []
    
    async def get_cached_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Кэшированное получение информации о пользователе"""
        return await self.get_user_info(user_id)
    
    async def notify_lesson_created(
        self,
        lesson_id: int,
        teacher_id: int,
        student_ids: List[int],
        lesson_datetime: str,
        studio_name: str,
        room_name: str
    ) -> bool:
        """
        Уведомление Auth Service о создании урока
        
        Args:
            lesson_id: ID урока
            teacher_id: ID преподавателя
            student_ids: Список ID учеников
            lesson_datetime: Дата и время урока
            studio_name: Название студии
            room_name: Название кабинета
            
        Returns:
            True если уведомление отправлено успешно
        """
        try:
            notification_data = {
                "lesson_id": lesson_id,
                "teacher_id": teacher_id,
                "student_ids": student_ids,
                "lesson_datetime": lesson_datetime,
                "studio_name": studio_name,
                "room_name": room_name
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/notifications/lesson-created",
                    headers=self.headers,
                    json=notification_data
                )
                
                if response.status_code in [200, 202]:
                    logger.info(f"Lesson creation notification sent: {lesson_id}")
                    return True
                else:
                    logger.warning(f"Failed to send lesson notification: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending lesson notification: {e}")
            return False
    
    async def notify_lesson_cancelled(
        self,
        lesson_id: int,
        teacher_id: int,
        student_ids: List[int],
        cancellation_reason: str
    ) -> bool:
        """
        Уведомление об отмене урока
        
        Args:
            lesson_id: ID урока
            teacher_id: ID преподавателя  
            student_ids: Список ID учеников
            cancellation_reason: Причина отмены
            
        Returns:
            True если уведомление отправлено успешно
        """
        try:
            notification_data = {
                "lesson_id": lesson_id,
                "teacher_id": teacher_id,
                "student_ids": student_ids,
                "cancellation_reason": cancellation_reason
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/notifications/lesson-cancelled",
                    headers=self.headers,
                    json=notification_data
                )
                
                if response.status_code in [200, 202]:
                    logger.info(f"Lesson cancellation notification sent: {lesson_id}")
                    return True
                else:
                    logger.warning(f"Failed to send cancellation notification: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending cancellation notification: {e}")
            return False
    
    async def health_check(self) -> bool:
        """
        Проверка доступности Auth Service
        
        Returns:
            True если Auth Service доступен
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Auth Service health check failed: {e}")
            return False
    
    async def invalidate_user_cache(self, user_id: int) -> bool:
        """Инвалидация кэша пользователя"""
        return await redis_cache_service.invalidate_user_all_cache(user_id)
    
    async def invalidate_studio_cache(self, studio_id: int) -> bool:
        """Инвалидация кэша студии"""
        return await redis_cache_service.invalidate_studio_cache(studio_id)
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Получение статистики кэша Auth интеграции"""
        return await redis_cache_service.get_cache_stats()


# Глобальный экземпляр для использования в dependencies
auth_service = AuthServiceIntegration()