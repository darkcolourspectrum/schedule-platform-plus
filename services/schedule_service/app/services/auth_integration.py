from typing import Optional, Dict, Any, List
import httpx
import logging
from functools import lru_cache

from app.config import settings
from app.core.exceptions import AuthServiceUnavailableException

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
        """Получение информации о пользователе по ID"""
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"Failed to get user info: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            raise AuthServiceUnavailableException()
    
    async def get_teacher_studios(self, teacher_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка студий, к которым имеет доступ преподаватель
        
        Returns:
            Список студий с базовой информацией
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/teachers/{teacher_id}/studios",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Failed to get teacher studios: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting teacher studios: {e}")
            # В случае ошибки возвращаем пустой список, а не прерываем работу
            return []
    
    async def get_all_studios(self) -> List[Dict[str, Any]]:
        """Получение всех студий из Auth Service для синхронизации"""
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/studios",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to get studios: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting studios: {e}")
            raise AuthServiceUnavailableException()
    
    async def get_students_by_ids(self, student_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Получение информации о нескольких учениках по их ID
        
        Returns:
            Словарь {student_id: student_data}
        """
        if not student_ids:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/users/batch",
                    headers=self.headers,
                    json={"user_ids": student_ids}
                )
                
                if response.status_code == 200:
                    users = response.json()
                    return {user["id"]: user for user in users}
                else:
                    logger.error(f"Failed to get students: {response.status_code}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Error getting students: {e}")
            return {}
    
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
    
    @lru_cache(maxsize=100, ttl=300)  # Кэшируем на 5 минут
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
        (для отправки уведомлений ученикам)
        """
        try:
            notification_data = {
                "lesson_id": lesson_id,
                "teacher_id": teacher_id,
                "student_ids": student_ids,
                "lesson_datetime": lesson_datetime,
                "studio_name": studio_name,
                "room_name": room_name,
                "type": "lesson_created"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/notifications/lesson-created",
                    headers=self.headers,
                    json=notification_data
                )
                
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Error sending lesson notification: {e}")
            return False
    
    async def notify_lesson_cancelled(
        self,
        lesson_id: int,
        student_ids: List[int],
        reason: str,
        cancelled_by_teacher: bool = True
    ) -> bool:
        """Уведомление об отмене урока"""
        
        try:
            notification_data = {
                "lesson_id": lesson_id,
                "student_ids": student_ids,
                "reason": reason,
                "cancelled_by_teacher": cancelled_by_teacher,
                "type": "lesson_cancelled"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/notifications/lesson-cancelled",
                    headers=self.headers,
                    json=notification_data
                )
                
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Error sending cancellation notification: {e}")
            return False


# Глобальный экземпляр для использования в приложении
auth_service = AuthServiceIntegration()