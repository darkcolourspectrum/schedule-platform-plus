"""
Общие схемы данных для shared/auth_lib
"""

from typing import Optional, Union, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """
    Унифицированная схема payload JWT-токена.
    
    Использует поле user_id как канонический идентификатор пользователя.
    Метод get_user_id() поддерживает обратную совместимость со старым
    форматом, где использовалось поле id.
    """
    
    user_id: int = Field(..., description="ID пользователя")
    email: str = Field(..., description="Email пользователя")
    role: Union[str, Dict[str, Any]] = Field(..., description="Роль (строка или dict)")
    studio_id: Optional[int] = Field(None, description="ID студии пользователя")
    
    jti: str = Field(..., description="Уникальный ID токена")
    exp: int = Field(..., description="Время истечения (Unix timestamp)")
    iat: int = Field(..., description="Время выдачи (Unix timestamp)")
    type: str = Field("access", description="Тип токена: access или refresh")
    
    model_config = {"extra": "allow"}
    
    @property
    def role_name(self) -> str:
        """Извлечение имени роли в едином формате."""
        if isinstance(self.role, dict):
            return self.role.get("name", "student")
        if self.role is None:
            return "student"
        return str(self.role)
    
    @property
    def issued_at(self) -> datetime:
        """Время выдачи токена как datetime."""
        return datetime.utcfromtimestamp(self.iat)
    
    @property
    def expires_at(self) -> datetime:
        """Время истечения токена как datetime."""
        return datetime.utcfromtimestamp(self.exp)
    
    @property
    def is_access_token(self) -> bool:
        """Является ли токен access-токеном."""
        return self.type == "access"