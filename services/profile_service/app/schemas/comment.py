"""
Pydantic схемы для комментариев и отзывов
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

from app.models.comment import CommentType, CommentStatus


class CommentBase(BaseModel):
    """Базовая схема комментария"""
    content: str = Field(..., min_length=10, max_length=1000, description="Текст комментария")
    title: Optional[str] = Field(None, max_length=200, description="Заголовок комментария")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Рейтинг от 1 до 5")
    is_anonymous: bool = Field(False, description="Анонимный комментарий")
    
    @validator('content')
    def validate_content(cls, v):
        """Валидация контента"""
        if not v or not v.strip():
            raise ValueError('Content cannot be empty')
        return v.strip()


class CommentCreate(CommentBase):
    """Схема для создания комментария"""
    target_type: str = Field(..., description="Тип объекта (teacher, student, lesson, profile)")
    target_id: int = Field(..., description="ID объекта")
    comment_type: CommentType = Field(..., description="Тип комментария")


class CommentUpdate(BaseModel):
    """Схема для обновления комментария"""
    content: Optional[str] = Field(None, min_length=10, max_length=1000)
    title: Optional[str] = Field(None, max_length=200)
    rating: Optional[int] = Field(None, ge=1, le=5)
    edit_reason: Optional[str] = Field(None, max_length=500, description="Причина редактирования")
    
    @validator('content')
    def validate_content(cls, v):
        """Валидация контента"""
        if v is not None and (not v or not v.strip()):
            raise ValueError('Content cannot be empty')
        return v.strip() if v else v


class AuthorInfo(BaseModel):
    """Информация об авторе комментария"""
    id: Optional[int] = None
    first_name: str = ""
    last_name: str = ""
    role: str = ""
    is_verified: bool = False


class CommentResponse(BaseModel):
    """Схема ответа с комментарием"""
    id: int
    target_type: str
    target_id: int
    comment_type: CommentType
    content: str
    title: Optional[str] = None
    rating: Optional[int] = None
    status: CommentStatus
    is_anonymous: bool
    is_verified: bool
    
    # Информация об авторе
    author: AuthorInfo
    
    # Редактирование
    edited_at: Optional[datetime] = None
    edit_reason: Optional[str] = None
    
    # Временные метки
    created_at: datetime
    updated_at: datetime
    
    # Вычисляемые поля
    is_recent: bool = False
    is_editable: bool = False


class CommentListResponse(BaseModel):
    """Схема списка комментариев"""
    comments: List[CommentResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class ReviewCreate(CommentBase):
    """Схема для создания отзыва о преподавателе"""
    teacher_id: int = Field(..., description="ID преподавателя")
    rating: int = Field(..., ge=1, le=5, description="Рейтинг от 1 до 5 (обязательно)")


class ReviewResponse(CommentResponse):
    """Схема ответа с отзывом"""
    teacher_id: int


class RatingStats(BaseModel):
    """Статистика рейтинга"""
    total_reviews: int = 0
    average_rating: float = 0.0
    min_rating: int = 0
    max_rating: int = 0
    rating_distribution: Dict[str, int] = Field(default_factory=dict)


class TeacherReviewsResponse(BaseModel):
    """Схема ответа с отзывами о преподавателе"""
    teacher_id: int
    rating_stats: RatingStats
    reviews: List[CommentResponse]
    total_reviews: int


class AdminNoteCreate(BaseModel):
    """Схема для создания административной заметки"""
    target_type: str = Field(..., description="Тип объекта (student, teacher, profile)")
    target_id: int = Field(..., description="ID объекта")
    content: str = Field(..., min_length=1, max_length=1000, description="Текст заметки")
    title: Optional[str] = Field(None, max_length=200, description="Заголовок заметки")


class CommentModerationRequest(BaseModel):
    """Схема запроса на модерацию комментария"""
    action: str = Field(..., description="Действие: hide, restore, delete, verify")
    reason: Optional[str] = Field(None, max_length=500, description="Причина модерации")
    
    @validator('action')
    def validate_action(cls, v):
        """Валидация действия модерации"""
        allowed_actions = ['hide', 'restore', 'delete', 'verify']
        if v not in allowed_actions:
            raise ValueError(f'Action must be one of: {", ".join(allowed_actions)}')
        return v


class LessonCommentCreate(BaseModel):
    """Схема для создания комментария к уроку"""
    lesson_id: int = Field(..., description="ID урока")
    content: str = Field(..., min_length=10, max_length=1000, description="Текст комментария")
    title: Optional[str] = Field(None, max_length=200, description="Заголовок")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Оценка урока")


class CommentStatsResponse(BaseModel):
    """Статистика комментариев"""
    total_comments: int
    public_reviews: int
    admin_notes: int
    lesson_comments: int
    recent_comments_count: int


class RecentCommentsResponse(BaseModel):
    """Недавние комментарии"""
    comments: List[CommentResponse]
    count: int


class CommentTargetInfo(BaseModel):
    """Информация о цели комментария"""
    type: str
    id: int
    title: Optional[str] = None
    description: Optional[str] = None


class UserCommentsResponse(BaseModel):
    """Комментарии пользователя"""
    comments: List[Dict[str, Any]] 
    total: int
    limit: int
    offset: int