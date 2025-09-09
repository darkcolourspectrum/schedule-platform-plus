"""
Сервис для создания персонализированных дашбордов пользователей
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.profile_repository import ProfileRepository
from app.repositories.comment_repository import CommentRepository
from app.repositories.activity_repository import ActivityRepository
from app.services.auth_client import auth_client
from app.services.schedule_client import schedule_client
from app.services.cache_service import cache_service
from app.config import settings

logger = logging.getLogger(__name__)


class DashboardService:
    """Сервис для создания персонализированных дашбордов"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.profile_repo = ProfileRepository(db)
        self.comment_repo = CommentRepository(db)
        self.activity_repo = ActivityRepository(db)
    
    async def get_dashboard(
        self, 
        user_id: int, 
        role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получение персонализированного дашборда пользователя
        
        Args:
            user_id: ID пользователя
            role: Роль пользователя (если известна, для оптимизации)
            
        Returns:
            Словарь с данными дашборда
        """
        try:
            # Получаем данные пользователя из Auth Service
            user_data = await auth_client.get_user_by_id(user_id)
            if not user_data:
                logger.warning(f"Пользователь {user_id} не найден в Auth Service")
                return {"error": "User not found"}
            
            user_role = role or user_data.get("role", {}).get("name", "")
            
            # Проверяем кэш
            cache_key = f"dashboard:{user_role}:{user_id}"
            cached_dashboard = await cache_service.get(cache_key)
            if cached_dashboard:
                logger.debug(f"Дашборд пользователя {user_id} получен из кэша")
                return cached_dashboard
            
            # Создаем дашборд в зависимости от роли
            if user_role == "student":
                dashboard = await self._build_student_dashboard(user_id, user_data)
            elif user_role == "teacher":
                dashboard = await self._build_teacher_dashboard(user_id, user_data)
            elif user_role == "admin":
                dashboard = await self._build_admin_dashboard(user_id, user_data)
            else:
                dashboard = await self._build_default_dashboard(user_id, user_data)
            
            # Кэшируем результат
            await cache_service.set(
                cache_key, 
                dashboard, 
                settings.cache_dashboard_ttl
            )
            
            logger.debug(f"Создан дашборд для пользователя {user_id} ({user_role})")
            return dashboard
            
        except Exception as e:
            logger.error(f"Ошибка создания дашборда для пользователя {user_id}: {e}")
            return {"error": "Failed to build dashboard"}
    
    async def _build_student_dashboard(
        self, 
        user_id: int, 
        user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Создание дашборда для студента"""
        try:
            # Базовая информация
            dashboard = {
                "user_info": await self._get_user_info(user_id, user_data),
                "role": "student",
                "dashboard_type": "student"
            }
            
            # Предстоящие уроки
            upcoming_lessons = await schedule_client.get_upcoming_lessons(
                user_id=user_id, 
                limit=settings.max_upcoming_lessons
            )
            dashboard["upcoming_lessons"] = {
                "lessons": upcoming_lessons,
                "count": len(upcoming_lessons)
            }
            
            # История уроков
            lesson_history = await schedule_client.get_lesson_history(
                user_id=user_id, 
                limit=10
            )
            dashboard["lesson_history"] = {
                "lessons": lesson_history,
                "total_completed": len(lesson_history)
            }
            
            # Недавняя активность
            recent_activities = await self.activity_repo.get_recent_activities(
                user_id=user_id,
                days=7,
                limit=settings.max_recent_activities
            )
            dashboard["recent_activities"] = [
                activity.to_dict_public() for activity in recent_activities
            ]
            
            # Мои комментарии и отзывы
            my_comments = await self.comment_repo.get_user_comments(
                author_id=user_id,
                limit=5
            )
            dashboard["my_comments"] = {
                "comments": [comment.to_dict_public() for comment in my_comments],
                "count": len(my_comments)
            }
            
            # Доступные преподаватели для записи
            available_teachers = await schedule_client.get_available_teachers()
            dashboard["available_teachers"] = {
                "teachers": available_teachers[:5],  # Показываем топ-5
                "total": len(available_teachers)
            }
            
            # Статистика студента
            stats = await self._get_student_stats(user_id)
            dashboard["statistics"] = stats
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Ошибка создания дашборда студента {user_id}: {e}")
            return {"error": "Failed to build student dashboard"}
    
    async def _build_teacher_dashboard(
        self, 
        user_id: int, 
        user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Создание дашборда для преподавателя"""
        try:
            dashboard = {
                "user_info": await self._get_user_info(user_id, user_data),
                "role": "teacher",
                "dashboard_type": "teacher"
            }
            
            # Расписание на сегодня
            today_schedule = await schedule_client.get_teacher_schedule(
                teacher_id=user_id,
                target_date=date.today()
            )
            dashboard["today_schedule"] = today_schedule
            
            # Предстоящие уроки
            upcoming_lessons = await schedule_client.get_upcoming_lessons(
                user_id=user_id,
                limit=settings.max_upcoming_lessons
            )
            dashboard["upcoming_lessons"] = {
                "lessons": upcoming_lessons,
                "count": len(upcoming_lessons)
            }
            
            # Статистика преподавателя
            teacher_stats = await schedule_client.get_teacher_statistics(user_id)
            dashboard["teaching_statistics"] = teacher_stats
            
            # Отзывы о преподавателе
            reviews_data = await self.comment_repo.get_teacher_rating_stats(user_id)
            recent_reviews = await self.comment_repo.get_public_reviews_for_teacher(
                teacher_id=user_id,
                limit=5
            )
            
            dashboard["reviews"] = {
                "rating_stats": reviews_data,
                "recent_reviews": [
                    {
                        **review.to_dict_public(),
                        "author": await self._get_review_author_info(review.author_id)
                    }
                    for review in recent_reviews
                ],
                "total_reviews": reviews_data.get("total_reviews", 0)
            }
            
            # Недавняя активность
            recent_activities = await self.activity_repo.get_recent_activities(
                user_id=user_id,
                days=7,
                limit=settings.max_recent_activities
            )
            dashboard["recent_activities"] = [
                activity.to_dict_public() for activity in recent_activities
            ]
            
            # Административные заметки (если есть)
            admin_notes = await self.comment_repo.get_admin_notes_for_user(
                user_id=user_id,
                limit=3
            )
            dashboard["admin_notes"] = [
                note.to_dict_admin() for note in admin_notes
            ]
            
            # Уведомления и быстрые действия
            dashboard["quick_actions"] = await self._get_teacher_quick_actions(user_id)
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Ошибка создания дашборда преподавателя {user_id}: {e}")
            return {"error": "Failed to build teacher dashboard"}
    
    async def _build_admin_dashboard(
        self, 
        user_id: int, 
        user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Создание дашборда для администратора"""
        try:
            dashboard = {
                "user_info": await self._get_user_info(user_id, user_data),
                "role": "admin",
                "dashboard_type": "admin"
            }
            
            # Общая статистика системы
            system_stats = await self._get_system_statistics()
            dashboard["system_statistics"] = system_stats
            
            # Недавние пользователи
            recent_users = await auth_client.get_users_by_role("student")  # Последние студенты
            dashboard["recent_users"] = recent_users[:10]
            
            # Недавние комментарии для модерации
            recent_comments = await self.comment_repo.get_recent_comments(limit=10)
            dashboard["recent_comments"] = [
                {
                    **comment.to_dict_admin(),
                    "author": await self._get_review_author_info(comment.author_id)
                }
                for comment in recent_comments
            ]
            
            # Системная активность
            system_activities = await self.activity_repo.get_system_activities(limit=20)
            dashboard["system_activities"] = [
                activity.to_dict_admin() for activity in system_activities
            ]
            
            # Статистика по преподавателям
            teachers = await auth_client.get_users_by_role("teacher")
            teacher_stats = []
            for teacher in teachers[:5]:  # Топ-5 преподавателей
                teacher_rating = await self.comment_repo.get_teacher_rating_stats(teacher["id"])
                teacher_stats.append({
                    "teacher": teacher,
                    "rating": teacher_rating
                })
            dashboard["top_teachers"] = teacher_stats
            
            # Быстрые действия администратора
            dashboard["admin_actions"] = await self._get_admin_quick_actions()
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Ошибка создания дашборда администратора {user_id}: {e}")
            return {"error": "Failed to build admin dashboard"}
    
    async def _build_default_dashboard(
        self, 
        user_id: int, 
        user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Создание базового дашборда"""
        try:
            dashboard = {
                "user_info": await self._get_user_info(user_id, user_data),
                "role": user_data.get("role", {}).get("name", "guest"),
                "dashboard_type": "default"
            }
            
            # Базовая информация о системе
            dashboard["welcome_message"] = "Добро пожаловать в Schedule Platform Plus!"
            
            # Недавняя активность пользователя
            recent_activities = await self.activity_repo.get_recent_activities(
                user_id=user_id,
                days=7,
                limit=5
            )
            dashboard["recent_activities"] = [
                activity.to_dict_public() for activity in recent_activities
            ]
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Ошибка создания базового дашборда для пользователя {user_id}: {e}")
            return {"error": "Failed to build default dashboard"}
    
    # Вспомогательные методы
    
    async def _get_user_info(self, user_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Получение информации о пользователе для дашборда"""
        try:
            profile = await self.profile_repo.get_by_user_id(user_id)
            
            user_info = {
                "id": user_id,
                "email": user_data.get("email"),
                "first_name": user_data.get("first_name"),
                "last_name": user_data.get("last_name"),
                "role": user_data.get("role", {}),
                "is_verified": user_data.get("is_verified", False)
            }
            
            if profile:
                user_info.update({
                    "display_name": profile.display_name,
                    "avatar_url": profile.avatar_url,
                    "bio": profile.bio,
                    "last_activity": profile.last_activity
                })
            
            return user_info
            
        except Exception as e:
            logger.error(f"Ошибка получения информации пользователя {user_id}: {e}")
            return {"id": user_id, "error": "Failed to load user info"}
    
    async def _get_student_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики студента"""
        try:
            # Статистика уроков
            all_lessons = await schedule_client.get_user_lessons(user_id)
            
            completed_lessons = [l for l in all_lessons if l.get("status") == "completed"]
            cancelled_lessons = [l for l in all_lessons if l.get("status") == "cancelled"]
            
            # Статистика активности
            activity_stats = await self.activity_repo.get_activity_statistics(user_id, days=30)
            
            return {
                "total_lessons": len(all_lessons),
                "completed_lessons": len(completed_lessons),
                "cancelled_lessons": len(cancelled_lessons),
                "activity_stats": activity_stats,
                "completion_rate": (
                    len(completed_lessons) / len(all_lessons) * 100 
                    if all_lessons else 0
                )
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики студента {user_id}: {e}")
            return {}
    
    async def _get_teacher_quick_actions(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение быстрых действий для преподавателя"""
        try:
            actions = [
                {
                    "id": "view_schedule",
                    "title": "Посмотреть расписание",
                    "description": "Расписание на сегодня и ближайшие дни",
                    "url": f"/schedule/teacher/{user_id}",
                    "icon": "calendar"
                },
                {
                    "id": "view_students",
                    "title": "Мои студенты",
                    "description": "Список активных студентов",
                    "url": f"/students/my",
                    "icon": "users"
                },
                {
                    "id": "view_reviews",
                    "title": "Отзывы обо мне",
                    "description": "Просмотр и ответ на отзывы",
                    "url": f"/reviews/teacher/{user_id}",
                    "icon": "star"
                }
            ]
            
            return actions
            
        except Exception as e:
            logger.error(f"Ошибка получения быстрых действий преподавателя {user_id}: {e}")
            return []
    
    async def _get_admin_quick_actions(self) -> List[Dict[str, Any]]:
        """Получение быстрых действий для администратора"""
        try:
            actions = [
                {
                    "id": "manage_users",
                    "title": "Управление пользователями",
                    "description": "Добавление, редактирование пользователей",
                    "url": "/admin/users",
                    "icon": "users"
                },
                {
                    "id": "moderate_comments",
                    "title": "Модерация комментариев",
                    "description": "Проверка и модерация отзывов",
                    "url": "/admin/comments",
                    "icon": "message-circle"
                },
                {
                    "id": "system_stats",
                    "title": "Статистика системы",
                    "description": "Аналитика и отчеты",
                    "url": "/admin/statistics",
                    "icon": "bar-chart"
                },
                {
                    "id": "manage_schedule",
                    "title": "Управление расписанием",
                    "description": "Настройка слотов и расписания",
                    "url": "/admin/schedule",
                    "icon": "calendar"
                }
            ]
            
            return actions
            
        except Exception as e:
            logger.error("Ошибка получения быстрых действий администратора")
            return []
    
    async def _get_system_statistics(self) -> Dict[str, Any]:
        """Получение общей статистики системы"""
        try:
            # Статистика пользователей
            all_students = await auth_client.get_users_by_role("student")
            all_teachers = await auth_client.get_users_by_role("teacher")
            
            # Статистика профилей
            total_profiles = await self.profile_repo.count()
            public_profiles = await self.profile_repo.count(is_profile_public=True)
            
            # Статистика комментариев
            total_comments = await self.comment_repo.count()
            
            # Статистика активности
            total_activities = await self.activity_repo.count()
            
            return {
                "users": {
                    "total_students": len(all_students),
                    "total_teachers": len(all_teachers),
                    "total_users": len(all_students) + len(all_teachers)
                },
                "profiles": {
                    "total_profiles": total_profiles,
                    "public_profiles": public_profiles,
                    "private_profiles": total_profiles - public_profiles
                },
                "content": {
                    "total_comments": total_comments,
                    "total_activities": total_activities
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения системной статистики: {e}")
            return {}
    
    async def _get_review_author_info(self, author_id: int) -> Dict[str, Any]:
        """Получение информации об авторе отзыва"""
        try:
            author_data = await auth_client.get_user_by_id(author_id)
            if author_data:
                return {
                    "id": author_data["id"],
                    "first_name": author_data.get("first_name", ""),
                    "last_name": author_data.get("last_name", ""),
                    "role": author_data.get("role", {}).get("name", "")
                }
            else:
                return {"id": None, "first_name": "Неизвестный", "last_name": "", "role": ""}
                
        except Exception as e:
            logger.error(f"Ошибка получения информации об авторе {author_id}: {e}")
            return {"id": None, "first_name": "Ошибка", "last_name": "", "role": ""}