"""
Сервис проверки доступа пользователей к студиям.

Текущая реализация: пользователь привязан к одной студии через User.studio_id.
Будущая реализация: many-to-many через таблицу user_studios.
Логика endpoints не должна зависеть от того, как реализована эта связь —
для этого все проверки идут через этот сервис.
"""

from typing import List, Optional


def _extract_role_name(role) -> str:
    if isinstance(role, dict):
        return role.get("name", "")
    return str(role) if role else ""


def get_user_accessible_studio_ids(user: dict) -> Optional[List[int]]:
    """
    Вернуть список ID студий, к которым у пользователя есть доступ.
    
    Returns:
        None     — пользователь имеет доступ ко всем студиям (admin).
        []       — у пользователя нет доступа ни к одной студии.
        [1,2,3]  — пользователь имеет доступ к этим студиям.
    """
    role = _extract_role_name(user.get("role"))
    
    if role == "admin":
        return None
    
    studio_id = user.get("studio_id")
    if studio_id is None:
        return []
    
    return [studio_id]


def user_has_access_to_studio(user: dict, studio_id: int) -> bool:
    """Проверить есть ли у пользователя доступ к конкретной студии."""
    accessible = get_user_accessible_studio_ids(user)
    if accessible is None:
        return True
    return studio_id in accessible