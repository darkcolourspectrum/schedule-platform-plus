"""Pydantic schemas for Notification API"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    """Схема создания уведомления (используется внутренне)"""
    user_id: int
    type: str
    title: str
    message: str
    payload: Optional[Dict[str, Any]] = None


class NotificationResponse(BaseModel):
    """Схема ответа с уведомлением"""
    id: int
    user_id: int
    type: str
    title: str
    message: str
    payload: Optional[Dict[str, Any]] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Список уведомлений с пагинацией"""
    notifications: List[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Только число непрочитанных (для badge в Header)"""
    unread_count: int


class MarkReadResponse(BaseModel):
    """Ответ на отметку 'прочитано'"""
    success: bool
    message: str