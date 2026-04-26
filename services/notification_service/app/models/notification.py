"""Notification model"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    """
    Уведомление пользователя.
    
    Поле type определяет шаблон уведомления (lesson_created, lesson_cancelled,
    lesson_reminder и т.д.). Поле payload хранит JSON с деталями события.
    """
    
    __tablename__ = "notifications"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Кому адресовано
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Тип уведомления (для рендера на фронте и фильтрации)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Заголовок и текст (готовые к показу)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    
    # Дополнительные данные (lesson_id, studio_id и т.п.) - для роутинга по клику
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Статус
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "is_read"),
    )
    
    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type})>"