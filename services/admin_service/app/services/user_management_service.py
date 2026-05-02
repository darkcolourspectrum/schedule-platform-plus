"""
User Management Service.

Изменения версии event-driven:
    - Чтение пользователей: из локальной users_cache (через UserCacheService).
    - Запись (роль, активность, привязка к студии): HTTP-вызовы к Auth Service
      (через AuthServiceClient). Auth Service сам публикует события и сам
      отзывает access-токены пользователя.

Локальный users_cache обновится через consumer событий 'auth_events'
(см. app/messaging/auth_consumer.py) - обычно в течение 1-2 секунд после
завершения HTTP-вызова.

Ответы клиенту мы формируем по данным, полученным от Auth Service в HTTP-ответе,
а не из локального кеша - так клиент видит свежее состояние сразу,
без ожидания доставки события через RabbitMQ.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal
from app.models.studio import Studio
from app.services.user_cache_service import user_cache_service
from app.services.auth_client import auth_client, AuthServiceUserNotFound, AuthServiceError

logger = logging.getLogger(__name__)


# Маппинг имён ролей в id - дублирует знание из Auth Service.
# Здесь оставлен для прозрачности, но в новой схеме мы передаём в Auth
# имя роли строкой, и Auth сам резолвит id через RoleRepository. Этот
# словарь используется только для формирования ответа клиенту.
_ROLE_NAME_TO_ID = {
    "admin": 1,
    "teacher": 2,
    "student": 3,
    "guest": 4,
}


class UserManagementService:
    """Управление пользователями (admin-операции)."""
    
    async def get_users_list(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
        studio_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Получить список пользователей с фильтрами из локального users_cache."""
        users = await user_cache_service.get_all_users(
            limit=limit,
            offset=offset,
            role_name=role,
            studio_id=studio_id,
            is_active=is_active,
        )
        
        # Обогащаем studio_name из Admin БД
        studio_ids = [u["studio_id"] for u in users if u.get("studio_id")]
        studio_map = await self._get_studio_names(studio_ids) if studio_ids else {}
        
        for u in users:
            u["studio_name"] = studio_map.get(u.get("studio_id"))
        
        return users
    
    async def update_user_role(self, user_id: int, role: str) -> Dict[str, Any]:
        """Изменить роль пользователя через Auth Service."""
        try:
            user_data = await auth_client.change_role(user_id, role)
        except AuthServiceUserNotFound:
            raise ValueError("User not found")
        except AuthServiceError as exc:
            raise RuntimeError(f"Failed to change role: {exc}") from exc
        
        return self._enrich_user_response(user_data)
    
    async def assign_user_to_studio(self, user_id: int, studio_id: int) -> Dict[str, Any]:
        """Привязать пользователя к студии через Auth Service."""
        # Проверяем, что студия существует в Admin БД (Auth не знает о студиях)
        studio_name = await self._get_studio_name(studio_id)
        if studio_name is None:
            raise ValueError(f"Studio {studio_id} not found")
        
        try:
            user_data = await auth_client.assign_studio(user_id, studio_id)
        except AuthServiceUserNotFound:
            raise ValueError("User not found")
        except AuthServiceError as exc:
            raise RuntimeError(f"Failed to assign studio: {exc}") from exc
        
        result = self._enrich_user_response(user_data)
        result["studio_name"] = studio_name
        return result
    
    async def activate_user(self, user_id: int) -> Dict[str, Any]:
        """Активировать пользователя через Auth Service."""
        try:
            user_data = await auth_client.activate(user_id)
        except AuthServiceUserNotFound:
            raise ValueError("User not found")
        except AuthServiceError as exc:
            raise RuntimeError(f"Failed to activate user: {exc}") from exc
        
        return self._enrich_user_response(user_data)
    
    async def deactivate_user(self, user_id: int) -> Dict[str, Any]:
        """Деактивировать пользователя через Auth Service."""
        try:
            user_data = await auth_client.deactivate(user_id)
        except AuthServiceUserNotFound:
            raise ValueError("User not found")
        except AuthServiceError as exc:
            raise RuntimeError(f"Failed to deactivate user: {exc}") from exc
        
        return self._enrich_user_response(user_data)
    
    async def _get_studio_name(self, studio_id: int) -> Optional[str]:
        """Получить имя студии по ID из Admin БД."""
        async with AdminAsyncSessionLocal() as session:
            result = await session.execute(
                select(Studio.name).where(Studio.id == studio_id)
            )
            return result.scalar_one_or_none()
    
    async def _get_studio_names(self, studio_ids: list[int]) -> Dict[int, str]:
        """Получить имена студий батчем для обогащения списков пользователей."""
        if not studio_ids:
            return {}
        async with AdminAsyncSessionLocal() as session:
            result = await session.execute(
                select(Studio.id, Studio.name).where(Studio.id.in_(studio_ids))
            )
            return dict(result.all())
    
    def _enrich_user_response(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Привести ответ Auth Service (UserProfile) к формату,
        ожидаемому фронтом (UserDetailResponse).
        
        Auth возвращает поле 'role' как строку (имя роли), фронт ждёт
        вложенный объект {id, name, description}.
        """
        role_name = user_data.get("role", "student")
        if isinstance(role_name, dict):
            role_obj = role_name
            role_name = role_obj.get("name", "student")
        
        return {
            "id": user_data["id"],
            "email": user_data["email"],
            "first_name": user_data["first_name"],
            "last_name": user_data["last_name"],
            "full_name": f"{user_data['first_name']} {user_data['last_name']}".strip(),
            "phone": user_data.get("phone"),
            "role_id": _ROLE_NAME_TO_ID.get(role_name, 3),
            "role": role_name,
            "studio_id": user_data.get("studio_id"),
            "studio_name": user_data.get("studio_name"),
            "is_active": user_data["is_active"],
            "is_verified": user_data.get("is_verified", False),
            "login_attempts": 0,
            "locked_until": None,
            "last_login": user_data.get("last_login"),
            "created_at": user_data.get("created_at"),
            "privacy_policy_accepted": True,
            "privacy_policy_accepted_at": None,
        }