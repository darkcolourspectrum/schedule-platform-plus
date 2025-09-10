"""
Аутентификация и авторизация для Profile Service
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status

from app.services.auth_client import auth_client
from app.core.exceptions import (
    ProfileAccessDeniedException,
    AuthServiceUnavailableException
)

logger = logging.getLogger(__name__)


class AuthManager:
    """Менеджер аутентификации и авторизации"""
    
    @staticmethod
    async def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Верификация JWT токена через Auth Service
        
        Args:
            token: JWT токен
            
        Returns:
            Данные пользователя или None если токен недействителен
        """
        try:
            user_data = await auth_client.verify_token(token)
            return user_data
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None
    
    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение данных пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Данные пользователя или None
        """
        try:
            user_data = await auth_client.get_user_by_id(user_id)
            return user_data
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    @staticmethod
    def check_profile_access(
        profile_user_id: int,
        current_user: Optional[Dict[str, Any]],
        is_profile_public: bool = True
    ) -> bool:
        """
        Проверка доступа к профилю
        
        Args:
            profile_user_id: ID владельца профиля
            current_user: Текущий пользователь
            is_profile_public: Публичный ли профиль
            
        Returns:
            True если доступ разрешен
        """
        # Если профиль публичный - доступ разрешен всем
        if is_profile_public:
            return True
        
        # Если пользователь не авторизован - доступ только к публичным профилям
        if not current_user:
            return False
        
        current_user_id = current_user.get("id")
        current_user_role = current_user.get("role", {})
        
        # Владелец профиля всегда имеет доступ
        if current_user_id == profile_user_id:
            return True
        
        # Администратор имеет доступ ко всем профилям
        if current_user_role.get("is_admin", False):
            return True
        
        # Для приватных профилей доступ запрещен
        return False
    
    @staticmethod
    def check_comment_access(
        comment_author_id: int,
        current_user: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Проверка доступа к комментарию
        
        Args:
            comment_author_id: ID автора комментария
            current_user: Текущий пользователь
            
        Returns:
            True если доступ разрешен
        """
        if not current_user:
            return False
        
        current_user_id = current_user.get("id")
        current_user_role = current_user.get("role", {})
        
        # Автор комментария может его редактировать
        if current_user_id == comment_author_id:
            return True
        
        # Администратор может редактировать любые комментарии
        if current_user_role.get("is_admin", False):
            return True
        
        return False
    
    @staticmethod
    def check_admin_access(current_user: Optional[Dict[str, Any]]) -> bool:
        """
        Проверка админских прав
        
        Args:
            current_user: Текущий пользователь
            
        Returns:
            True если пользователь администратор
        """
        if not current_user:
            return False
        
        user_role = current_user.get("role", {})
        return user_role.get("is_admin", False)
    
    @staticmethod
    def check_teacher_access(current_user: Optional[Dict[str, Any]]) -> bool:
        """
        Проверка прав преподавателя
        
        Args:
            current_user: Текущий пользователь
            
        Returns:
            True если пользователь преподаватель или администратор
        """
        if not current_user:
            return False
        
        user_role = current_user.get("role", {})
        return user_role.get("is_teacher", False) or user_role.get("is_admin", False)
    
    @staticmethod
    def require_profile_access(
        profile_user_id: int,
        current_user: Optional[Dict[str, Any]],
        is_profile_public: bool = True
    ):
        """
        Требует доступ к профилю, выбрасывает исключение если доступ запрещен
        
        Args:
            profile_user_id: ID владельца профиля
            current_user: Текущий пользователь
            is_profile_public: Публичный ли профиль
            
        Raises:
            ProfileAccessDeniedException: Если доступ запрещен
        """
        if not AuthManager.check_profile_access(profile_user_id, current_user, is_profile_public):
            raise ProfileAccessDeniedException("You don't have access to this profile")
    
    @staticmethod
    def require_comment_access(
        comment_author_id: int,
        current_user: Optional[Dict[str, Any]]
    ):
        """
        Требует доступ к комментарию
        
        Args:
            comment_author_id: ID автора комментария
            current_user: Текущий пользователь
            
        Raises:
            ProfileAccessDeniedException: Если доступ запрещен
        """
        if not AuthManager.check_comment_access(comment_author_id, current_user):
            raise ProfileAccessDeniedException("You can only modify your own comments")
    
    @staticmethod
    def require_admin_access(current_user: Optional[Dict[str, Any]]):
        """
        Требует админские права
        
        Args:
            current_user: Текущий пользователь
            
        Raises:
            ProfileAccessDeniedException: Если не администратор
        """
        if not AuthManager.check_admin_access(current_user):
            raise ProfileAccessDeniedException("Admin access required")
    
    @staticmethod
    def require_teacher_access(current_user: Optional[Dict[str, Any]]):
        """
        Требует права преподавателя
        
        Args:
            current_user: Текущий пользователь
            
        Raises:
            ProfileAccessDeniedException: Если не преподаватель/администратор
        """
        if not AuthManager.check_teacher_access(current_user):
            raise ProfileAccessDeniedException("Teacher or admin access required")


class PermissionChecker:
    """Проверщик разрешений для различных операций"""
    
    @staticmethod
    def can_view_profile(
        profile_user_id: int,
        current_user: Optional[Dict[str, Any]],
        is_profile_public: bool = True
    ) -> bool:
        """Может ли пользователь просматривать профиль"""
        return AuthManager.check_profile_access(profile_user_id, current_user, is_profile_public)
    
    @staticmethod
    def can_edit_profile(
        profile_user_id: int,
        current_user: Optional[Dict[str, Any]]
    ) -> bool:
        """Может ли пользователь редактировать профиль"""
        if not current_user:
            return False
        
        current_user_id = current_user.get("id")
        current_user_role = current_user.get("role", {})
        
        # Владелец профиля или администратор
        return (current_user_id == profile_user_id or 
                current_user_role.get("is_admin", False))
    
    @staticmethod
    def can_delete_profile(
        profile_user_id: int,
        current_user: Optional[Dict[str, Any]]
    ) -> bool:
        """Может ли пользователь удалить профиль"""
        if not current_user:
            return False
        
        current_user_id = current_user.get("id")
        current_user_role = current_user.get("role", {})
        
        # Владелец профиля или администратор
        return (current_user_id == profile_user_id or 
                current_user_role.get("is_admin", False))
    
    @staticmethod
    def can_create_comment(
        current_user: Optional[Dict[str, Any]]
    ) -> bool:
        """Может ли пользователь создавать комментарии"""
        # Только авторизованные пользователи могут создавать комментарии
        return current_user is not None
    
    @staticmethod
    def can_view_private_comments(
        current_user: Optional[Dict[str, Any]]
    ) -> bool:
        """Может ли пользователь видеть приватные комментарии"""
        if not current_user:
            return False
        
        user_role = current_user.get("role", {})
        # Только администраторы и преподаватели видят приватные комментарии
        return (user_role.get("is_admin", False) or 
                user_role.get("is_teacher", False))