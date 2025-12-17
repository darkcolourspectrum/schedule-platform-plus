"""
HTTP клиент для взаимодействия с Admin Service
"""

import logging
from typing import Optional, Dict, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AdminServiceClient:
    """Клиент для взаимодействия с Admin Service"""
    
    def __init__(self):
        self.base_url = settings.admin_service_url
        self.timeout = settings.admin_service_timeout
        self.internal_api_key = settings.internal_api_key
    
    async def get_studio(self, studio_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о студии"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/studios/{studio_id}",
                    headers={
                        "X-Internal-API-Key": self.internal_api_key
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"Admin Service error: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get studio from Admin Service: {e}")
            return None
    
    async def get_classroom(self, classroom_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о кабинете"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/classrooms/{classroom_id}",
                    headers={
                        "X-Internal-API-Key": self.internal_api_key
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"Admin Service error: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get classroom from Admin Service: {e}")
            return None
    
    async def get_studios(self) -> list:
        """Получить список всех студий"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/studios",
                    headers={
                        "X-Internal-API-Key": self.internal_api_key
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Admin Service error: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to get studios from Admin Service: {e}")
            return []
    
    async def get_studio_classrooms(self, studio_id: int) -> list:
        """Получить все кабинеты студии"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/studios/{studio_id}/classrooms",
                    headers={
                        "X-Internal-API-Key": self.internal_api_key
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Admin Service error: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to get classrooms from Admin Service: {e}")
            return []


# Глобальный экземпляр клиента
admin_service_client = AdminServiceClient()
