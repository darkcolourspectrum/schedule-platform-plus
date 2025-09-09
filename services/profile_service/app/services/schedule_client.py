"""
HTTP клиент для интеграции с Schedule Service
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class ScheduleServiceClient:
    """Клиент для взаимодействия с Schedule Service"""
    
    def __init__(self):
        self.base_url = settings.schedule_service_url
        self.timeout = settings.schedule_service_timeout
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-API-Key": settings.internal_api_key
        }
    
    async def get_user_lessons(
        self, 
        user_id: int, 
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получение уроков пользователя
        
        Args:
            user_id: ID пользователя (студента или преподавателя)
            start_date: Начальная дата фильтра
            end_date: Конечная дата фильтра
            status: Статус урока (scheduled, completed, cancelled)
            
        Returns:
            List уроков
        """
        try:
            params = {"user_id": user_id}
            if start_date:
                params["start_date"] = start_date.isoformat()
            if end_date:
                params["end_date"] = end_date.isoformat()
            if status:
                params["status"] = status
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/lessons",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    lessons_data = response.json()
                    logger.debug(f"Получено {len(lessons_data)} уроков для пользователя {user_id}")
                    return lessons_data
                else:
                    logger.error(f"Ошибка получения уроков пользователя {user_id}: {response.status_code}")
                    return []
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Schedule Service: {self.base_url}")
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении уроков пользователя {user_id}: {e}")
            return []
    
    async def get_upcoming_lessons(self, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Получение предстоящих уроков пользователя
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество уроков
            
        Returns:
            List предстоящих уроков
        """
        today = date.today()
        lessons = await self.get_user_lessons(
            user_id=user_id,
            start_date=today,
            status="scheduled"
        )
        
        # Сортируем по дате и ограничиваем количество
        sorted_lessons = sorted(lessons, key=lambda x: x.get("start_time", ""))
        return sorted_lessons[:limit]
    
    async def get_lesson_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получение истории уроков пользователя
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество уроков
            
        Returns:
            List завершенных уроков
        """
        lessons = await self.get_user_lessons(
            user_id=user_id,
            end_date=date.today(),
            status="completed"
        )
        
        # Сортируем по дате (новые сначала) и ограничиваем количество
        sorted_lessons = sorted(lessons, key=lambda x: x.get("start_time", ""), reverse=True)
        return sorted_lessons[:limit]
    
    async def get_teacher_schedule(
        self, 
        teacher_id: int, 
        target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Получение расписания преподавателя на день
        
        Args:
            teacher_id: ID преподавателя
            target_date: Дата (по умолчанию сегодня)
            
        Returns:
            Dict с расписанием преподавателя
        """
        try:
            if not target_date:
                target_date = date.today()
            
            params = {
                "teacher_id": teacher_id,
                "date": target_date.isoformat()
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/teachers/{teacher_id}/schedule",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    schedule_data = response.json()
                    logger.debug(f"Получено расписание преподавателя {teacher_id} на {target_date}")
                    return schedule_data
                else:
                    logger.error(f"Ошибка получения расписания преподавателя {teacher_id}: {response.status_code}")
                    return {}
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Schedule Service: {self.base_url}")
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении расписания преподавателя {teacher_id}: {e}")
            return {}
    
    async def get_teacher_statistics(self, teacher_id: int) -> Dict[str, Any]:
        """
        Получение статистики преподавателя
        
        Args:
            teacher_id: ID преподавателя
            
        Returns:
            Dict со статистикой
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/teachers/{teacher_id}/statistics",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    stats_data = response.json()
                    logger.debug(f"Получена статистика преподавателя {teacher_id}")
                    return stats_data
                else:
                    logger.error(f"Ошибка получения статистики преподавателя {teacher_id}: {response.status_code}")
                    return {}
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Schedule Service: {self.base_url}")
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении статистики преподавателя {teacher_id}: {e}")
            return {}
    
    async def get_available_teachers(self, studio_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Получение списка доступных преподавателей
        
        Args:
            studio_id: ID студии (опционально)
            
        Returns:
            List преподавателей
        """
        try:
            params = {}
            if studio_id:
                params["studio_id"] = studio_id
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/teachers",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    teachers_data = response.json()
                    logger.debug(f"Получено {len(teachers_data)} преподавателей")
                    return teachers_data
                else:
                    logger.error(f"Ошибка получения списка преподавателей: {response.status_code}")
                    return []
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Schedule Service: {self.base_url}")
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении списка преподавателей: {e}")
            return []
    
    async def health_check(self) -> bool:
        """
        Проверка доступности Schedule Service
        
        Returns:
            bool: True если сервис доступен
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False


# Глобальный экземпляр клиента
schedule_client = ScheduleServiceClient()