"""
HTTP клиент для интеграции с Auth Service
"""

import logging
from typing import Optional, List, Dict, Any
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class AuthServiceClient:
    """Клиент для взаимодействия с Auth Service"""
    
    def __init__(self):
        self.base_url = settings.auth_service_url
        self.timeout = settings.auth_service_timeout
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-API-Key": settings.internal_api_key
        }
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict с данными пользователя или None
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    logger.debug(f"Получен пользователь {user_id}: {user_data.get('email')}")
                    return user_data
                elif response.status_code == 404:
                    logger.warning(f"Пользователь {user_id} не найден в Auth Service")
                    return None
                else:
                    logger.error(f"Ошибка получения пользователя {user_id}: {response.status_code} - {response.text}")
                    return None
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Auth Service: {self.base_url}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя {user_id}: {e}")
            return None
    
    async def get_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        """
        Получение пользователей по роли
        
        Args:
            role: Роль пользователя (admin, teacher, student)
            
        Returns:
            List пользователей
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users",
                    headers=self.headers,
                    params={"role": role}
                )
                
                if response.status_code == 200:
                    users_data = response.json()
                    logger.debug(f"Получено {len(users_data)} пользователей с ролью {role}")
                    return users_data
                else:
                    logger.error(f"Ошибка получения пользователей по роли {role}: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей по роли {role}: {e}")
            return []
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Валидация JWT токена через Auth Service
        
        ИСПРАВЛЕНО: Теперь отправляем токен в заголовке Authorization
        
        Args:
            token: JWT токен
            
        Returns:
            Dict с данными токена или None
        """
        try:
            # ФИКС: Добавляем Bearer токен в заголовок Authorization
            headers = {
                **self.headers,  # Содержит X-Internal-API-Key
                "Authorization": f"Bearer {token}"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/validate-token",
                    headers=headers
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    logger.debug(f"Токен валиден для пользователя {token_data.get('user_id')}")
                    return token_data
                else:
                    logger.warning(f"Токен невалиден: {response.status_code} - {response.text}")
                    return None
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Auth Service: {self.base_url}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при валидации токена: {e}")
            return None
    
    async def get_user_permissions(self, user_id: int) -> List[str]:
        """
        Получение разрешений пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            List разрешений
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/permissions",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    permissions_data = response.json()
                    logger.debug(f"Получены разрешения для пользователя {user_id}")
                    return permissions_data.get("permissions", [])
                else:
                    logger.warning(f"Не удалось получить разрешения для пользователя {user_id}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении разрешений пользователя {user_id}: {e}")
            return []
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Верификация токена (алиас для validate_token для обратной совместимости)
        
        Args:
            token: JWT токен
            
        Returns:
            Dict с данными пользователя или None
        """
        return await self.validate_token(token)
    
    async def health_check(self) -> bool:
        """
        Проверка доступности Auth Service
        
        Returns:
            True если сервис доступен
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers=self.headers
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Auth Service недоступен: {e}")
            return False


# Глобальный singleton клиента
auth_client = AuthServiceClient()