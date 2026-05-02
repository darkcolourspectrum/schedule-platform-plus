"""
HTTP клиент для интеграции с Auth Service
"""

import logging
from typing import Optional, Dict, Any
import httpx
from app.config import settings
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.models.user_cache import UserCache

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
        Получение пользователя по ID.
        
        Сначала читаем из локального users_cache (быстро, не зависит
        от доступности Auth Service). Если в кеше нет - fallback на HTTP-вызов
        Auth Service. Это редкий случай: либо пользователь только что создан
        и событие user.created ещё не дошло, либо что-то рассинхронизировалось.
        """
        # 1. Чтение из локального кеша
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserCache).where(UserCache.id == user_id)
                )
                cached = result.scalar_one_or_none()
        except Exception as exc:
            logger.error(f"Ошибка чтения users_cache для user_id={user_id}: {exc}")
            cached = None
        
        if cached is not None:
            return {
                "id": cached.id,
                "email": cached.email,
                "first_name": cached.first_name,
                "last_name": cached.last_name,
                "phone": cached.phone,
                "role": {
                    "id": cached.role_id,
                    "name": cached.role_name,
                },
                "studio_id": cached.studio_id,
                "is_active": cached.is_active,
                "is_verified": cached.is_verified,
            }
        
        # 2. Fallback: HTTP к Auth Service
        logger.warning(
            f"User {user_id} not in users_cache, falling back to Auth HTTP"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Пользователь {user_id} не найден в Auth Service")
                    return None
                else:
                    logger.error(
                        f"Ошибка получения пользователя {user_id}: "
                        f"{response.status_code} - {response.text}"
                    )
                    return None
                    
        except httpx.ConnectError:
            logger.error(f"Не удалось подключиться к Auth Service: {self.base_url}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя {user_id}: {e}")
            return None
    
    
    
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