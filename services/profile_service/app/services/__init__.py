"""
Сервисы для Profile Service
"""
from app.services.auth_client import auth_client, AuthServiceClient
from app.services.cache_service import cache_service, CacheService
from app.services.profile_service import ProfileService
from app.services.avatar_service import avatar_service, AvatarService

__all__ = [
    # HTTP клиенты
    "auth_client",
    "AuthServiceClient",

    # Основные сервисы
    "ProfileService",

    # Вспомогательные сервисы
    "cache_service",
    "CacheService",
    "avatar_service",
    "AvatarService",
]