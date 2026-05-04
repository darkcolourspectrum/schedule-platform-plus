"""
Pydantic-схемы для membership endpoints.

Эти схемы возвращаются на API эндпоинтах /api/schedule/studios/...
и используются фронтом в модалках создания занятия и шаблона.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

class StudioInfo(BaseModel):
    """Краткая информация о студии для списка в UI."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    is_active: bool


class ClassroomInfo(BaseModel):
    """Краткая информация о кабинете."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    studio_id: int
    name: str
    capacity: int
    description: Optional[str] = None
    floor: Optional[int] = None
    room_number: Optional[str] = None
    is_active: bool


class StudioMemberInfo(BaseModel):
    """
    Член студии (преподаватель или ученик) для списка в UI.
    
    Формат совместим с тем, что фронт сейчас ожидает от admin-эндпоинта
    fetchAllUsers - чтобы переключение в модалках было минимальным.
    
    UserCache из schedule БД хранит роль в поле role_name. Через alias
    мы читаем его и отдаём наружу как 'role', сохраняя контракт фронта.
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: str = Field(validation_alias="role_name")
    studio_id: Optional[int] = None
    is_active: bool
    
    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class StudioMembersResponse(BaseModel):
    """
    Все члены студии одним запросом.
    
    Фронт получает учителей и учеников за один запрос - это удобнее,
    чем делать два отдельных вызова и потом сшивать на клиенте.
    """
    
    studio_id: int
    teachers: List[StudioMemberInfo]
    students: List[StudioMemberInfo]