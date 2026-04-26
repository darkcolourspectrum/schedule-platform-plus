"""
Security utilities for JWT token validation
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)


def extract_role_name(role_data: Any) -> str:
    """
    Извлечение имени роли из различных форматов
    
    Args:
        role_data: Данные роли (строка или dict)
        
    Returns:
        Имя роли
    """
    if isinstance(role_data, dict):
        return role_data.get("name", "student")
    return str(role_data)


def verify_internal_api_key(api_key: Optional[str]) -> bool:
    """
    Проверка Internal API Key для межсервисного взаимодействия
    
    Args:
        api_key: API ключ из заголовка
        
    Returns:
        True если ключ валидный
    """
    if not api_key:
        return False
    return api_key == settings.internal_api_key
