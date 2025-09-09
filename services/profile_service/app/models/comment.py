"""
Модель системы комментариев для Profile Service
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import BaseModel


class CommentType(str, enum.Enum):
    """Типы комментариев"""
    PUBLIC_REVIEW = "public_review"        # Публичный отзыв о преподавателе
    ADMIN_NOTE = "admin_note"              # Приватная заметка администратора
    LESSON_COMMENT = "lesson_comment"      # Комментарий к уроку
    PROFILE_COMMENT = "profile_comment"    # Комментарий к профилю


class CommentStatus(str, enum.Enum):
    """Статусы комментариев"""
    ACTIVE = "active"           # Активный
    HIDDEN = "hidden"           # Скрытый
    DELETED = "deleted"         # Удаленный
    MODERATED = "moderated"     # На модерации


class Comment(BaseModel):
    """
    Модель комментария
    Универсальная система для отзывов, заметок и комментариев
    """
    __tablename__ = "comments"
    
    # Автор комментария
    author_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="ID автора комментария (из Auth Service)"
    )
    
    # Цель комментария (к чему относится)
    target_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Тип объекта: teacher, student, lesson, profile"
    )
    
    target_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="ID объекта"
    )
    
    # Тип и содержание комментария
    comment_type: Mapped[CommentType] = mapped_column(
        Enum(CommentType),
        nullable=False,
        index=True,
        comment="Тип комментария"
    )
    
    title: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Заголовок комментария"
    )
    
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Текст комментария"
    )
    
    # Рейтинг (для отзывов)
    rating: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Рейтинг от 1 до 5 (для отзывов)"
    )
    
    # Статус и модерация
    status: Mapped[CommentStatus] = mapped_column(
        Enum(CommentStatus),
        default=CommentStatus.ACTIVE,
        nullable=False,
        index=True,
        comment="Статус комментария"
    )
    
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Анонимный комментарий"
    )
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Верифицированный комментарий"
    )
    
    # Модерация
    moderated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ID модератора"
    )
    
    moderated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время модерации"
    )
    
    # Редактирование
    edited_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время последнего редактирования"
    )
    
    edit_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Причина редактирования"
    )
    
    # Метаданные
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        Integer,  # JSON в SQLAlchemy
        nullable=True,
        comment="Дополнительные метаданные в JSON"
    )
    
    @property
    def is_public(self) -> bool:
        """Является ли комментарий публичным"""
        return (
            self.comment_type == CommentType.PUBLIC_REVIEW and 
            self.status == CommentStatus.ACTIVE
        )
    
    @property
    def is_editable(self) -> bool:
        """Можно ли редактировать комментарий"""
        if self.status != CommentStatus.ACTIVE:
            return False
        
        # Проверяем временные ограничения (24 часа)
        if self.created_at:
            time_diff = datetime.now() - self.created_at
            return time_diff.total_seconds() < 24 * 3600
        
        return False
    
    @property
    def is_recent(self) -> bool:
        """Является ли комментарий недавним (менее 1 часа)"""
        if self.created_at:
            time_diff = datetime.now() - self.created_at
            return time_diff.total_seconds() < 3600
        return False
    
    def mark_as_edited(self, reason: Optional[str] = None) -> None:
        """Отметить комментарий как отредактированный"""
        self.edited_at = datetime.now()
        if reason:
            self.edit_reason = reason
    
    def hide(self, moderator_id: Optional[int] = None) -> None:
        """Скрыть комментарий"""
        self.status = CommentStatus.HIDDEN
        if moderator_id:
            self.moderated_by = moderator_id
            self.moderated_at = datetime.now()
    
    def restore(self, moderator_id: Optional[int] = None) -> None:
        """Восстановить комментарий"""
        self.status = CommentStatus.ACTIVE
        if moderator_id:
            self.moderated_by = moderator_id
            self.moderated_at = datetime.now()
    
    def soft_delete(self, moderator_id: Optional[int] = None) -> None:
        """Мягкое удаление комментария"""
        self.status = CommentStatus.DELETED
        if moderator_id:
            self.moderated_by = moderator_id
            self.moderated_at = datetime.now()
    
    def verify(self, moderator_id: int) -> None:
        """Верифицировать комментарий"""
        self.is_verified = True
        self.moderated_by = moderator_id
        self.moderated_at = datetime.now()
    
    def to_dict_public(self) -> dict:
        """Публичное представление комментария"""
        result = self.to_dict(exclude_fields={
            'moderated_by', 
            'moderated_at',
            'metadata_json'
        })
        
        # Скрываем автора для анонимных комментариев
        if self.is_anonymous:
            result['author_id'] = None
        
        return result
    
    def to_dict_admin(self) -> dict:
        """Административное представление комментария"""
        return self.to_dict()
    
    def __repr__(self) -> str:
        return f"<Comment(id={self.id}, type={self.comment_type}, target={self.target_type}:{self.target_id})>"