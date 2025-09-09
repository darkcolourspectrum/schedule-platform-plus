"""
Pydantic схемы для дашбордов пользователей
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.schemas.profile import UserInfo
from app.schemas.comment import RatingStats, CommentResponse


class ActivityItem(BaseModel):
    """Элемент активности пользователя"""
    id: int
    activity_type: str
    title: str
    description: Optional[str] = None
    level: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    success: bool
    created_at: datetime
    time_ago: str
    is_important: bool
    is_recent: bool


class LessonInfo(BaseModel):
    """Информация об уроке"""
    id: int
    title: str
    start_time: datetime
    end_time: datetime
    status: str
    teacher_name: Optional[str] = None
    student_name: Optional[str] = None
    room: Optional[str] = None
    studio_name: Optional[str] = None


class UpcomingLessons(BaseModel):
    """Предстоящие уроки"""
    lessons: List[LessonInfo]
    count: int


class LessonHistory(BaseModel):
    """История уроков"""
    lessons: List[LessonInfo]
    total_completed: int


class TeacherInfo(BaseModel):
    """Информация о преподавателе"""
    id: int
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    specializations: List[str] = Field(default_factory=list)
    average_rating: float = 0.0
    total_reviews: int = 0


class AvailableTeachers(BaseModel):
    """Доступные преподаватели"""
    teachers: List[TeacherInfo]
    total: int


class StudentStats(BaseModel):
    """Статистика студента"""
    total_lessons: int = 0
    completed_lessons: int = 0
    cancelled_lessons: int = 0
    completion_rate: float = 0.0
    activity_stats: Dict[str, Any] = Field(default_factory=dict)


class TeachingStats(BaseModel):
    """Статистика преподавания"""
    total_lessons: int = 0
    total_students: int = 0
    average_rating: float = 0.0
    total_reviews: int = 0
    lessons_this_week: int = 0
    lessons_this_month: int = 0


class TodaySchedule(BaseModel):
    """Расписание на сегодня"""
    date: date
    lessons: List[LessonInfo]
    total_lessons: int
    free_slots: int


class ReviewsSummary(BaseModel):
    """Сводка отзывов"""
    rating_stats: RatingStats
    recent_reviews: List[CommentResponse]
    total_reviews: int


class MyComments(BaseModel):
    """Мои комментарии"""
    comments: List[CommentResponse]
    count: int


class QuickAction(BaseModel):
    """Быстрое действие"""
    id: str
    title: str
    description: str
    url: str
    icon: str


class SystemStats(BaseModel):
    """Системная статистика"""
    users: Dict[str, int]
    profiles: Dict[str, int]
    content: Dict[str, int]


class TopTeacher(BaseModel):
    """Топ преподаватель"""
    teacher: Dict[str, Any]
    rating: RatingStats


class AdminNoteItem(BaseModel):
    """Административная заметка"""
    id: int
    content: str
    title: Optional[str] = None
    created_at: datetime
    author_name: str


# Схемы дашбордов по ролям

class StudentDashboard(BaseModel):
    """Дашборд студента"""
    user_info: UserInfo
    role: str = "student"
    dashboard_type: str = "student"
    
    upcoming_lessons: UpcomingLessons
    lesson_history: LessonHistory
    recent_activities: List[ActivityItem]
    my_comments: MyComments
    available_teachers: AvailableTeachers
    statistics: StudentStats


class TeacherDashboard(BaseModel):
    """Дашборд преподавателя"""
    user_info: UserInfo
    role: str = "teacher"
    dashboard_type: str = "teacher"
    
    today_schedule: TodaySchedule
    upcoming_lessons: UpcomingLessons
    teaching_statistics: TeachingStats
    reviews: ReviewsSummary
    recent_activities: List[ActivityItem]
    admin_notes: List[AdminNoteItem]
    quick_actions: List[QuickAction]


class AdminDashboard(BaseModel):
    """Дашборд администратора"""
    user_info: UserInfo
    role: str = "admin"
    dashboard_type: str = "admin"
    
    system_statistics: SystemStats
    recent_users: List[Dict[str, Any]]
    recent_comments: List[CommentResponse]
    system_activities: List[ActivityItem]
    top_teachers: List[TopTeacher]
    admin_actions: List[QuickAction]


class DefaultDashboard(BaseModel):
    """Базовый дашборд"""
    user_info: UserInfo
    role: str
    dashboard_type: str = "default"
    
    welcome_message: str
    recent_activities: List[ActivityItem]


# Унифицированная схема ответа дашборда
class DashboardResponse(BaseModel):
    """Универсальная схема ответа дашборда"""
    user_info: UserInfo
    role: str
    dashboard_type: str
    data: Dict[str, Any]  # Содержимое дашборда в зависимости от роли
    generated_at: datetime = Field(default_factory=datetime.now)
    cached: bool = False


class DashboardError(BaseModel):
    """Ошибка дашборда"""
    error: str
    detail: Optional[str] = None