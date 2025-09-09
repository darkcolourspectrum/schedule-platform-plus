"""
Сервис для работы с комментариями и отзывами
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment, CommentType, CommentStatus
from app.models.activity import ActivityType, ActivityLevel
from app.repositories.comment_repository import CommentRepository
from app.repositories.activity_repository import ActivityRepository
from app.services.auth_client import auth_client
from app.services.cache_service import cache_service
from app.config import settings

logger = logging.getLogger(__name__)


class CommentService:
    """Сервис для работы с комментариями и отзывами"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.comment_repo = CommentRepository(db)
        self.activity_repo = ActivityRepository(db)
    
    async def create_comment(
        self,
        author_id: int,
        target_type: str,
        target_id: int,
        comment_type: CommentType,
        content: str,
        title: Optional[str] = None,
        rating: Optional[int] = None,
        is_anonymous: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создание нового комментария с валидацией и логированием
        
        Args:
            author_id: ID автора комментария
            target_type: Тип объекта (teacher, student, lesson, profile)
            target_id: ID объекта
            comment_type: Тип комментария
            content: Текст комментария
            title: Заголовок комментария
            rating: Рейтинг (для отзывов)
            is_anonymous: Анонимный комментарий
            ip_address: IP адрес пользователя
            user_agent: User-Agent пользователя
            
        Returns:
            Словарь с данными созданного комментария или None
        """
        try:
            # Валидация контента
            if not content or len(content.strip()) < 10:
                logger.warning(f"Попытка создать слишком короткий комментарий от пользователя {author_id}")
                return None
            
            if len(content) > settings.max_comment_length:
                logger.warning(f"Попытка создать слишком длинный комментарий от пользователя {author_id}")
                return None
            
            # Валидация рейтинга
            if rating is not None and (rating < 1 or rating > 5):
                logger.warning(f"Неверный рейтинг {rating} от пользователя {author_id}")
                return None
            
            # Проверяем существование автора
            author_data = await auth_client.get_user_by_id(author_id)
            if not author_data:
                logger.warning(f"Автор {author_id} не найден в Auth Service")
                return None
            
            # Создаем комментарий
            comment = await self.comment_repo.create_comment(
                author_id=author_id,
                target_type=target_type,
                target_id=target_id,
                comment_type=comment_type,
                content=content.strip(),
                title=title,
                rating=rating,
                is_anonymous=is_anonymous
            )
            
            if not comment:
                logger.error(f"Не удалось создать комментарий от пользователя {author_id}")
                return None
            
            # Логируем активность
            activity_title = "Создан комментарий"
            if comment_type == CommentType.PUBLIC_REVIEW:
                activity_title = "Оставлен отзыв"
            elif comment_type == CommentType.ADMIN_NOTE:
                activity_title = "Добавлена заметка администратора"
            
            await self.activity_repo.log_activity(
                user_id=author_id,
                activity_type=ActivityType.COMMENT_CREATED,
                title=activity_title,
                description=f"Комментарий к {target_type}:{target_id}",
                level=ActivityLevel.LOW,
                target_type=target_type,
                target_id=target_id,
                activity_data={
                    "comment_id": comment.id,
                    "comment_type": comment_type.value,
                    "has_rating": rating is not None
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Очищаем кэш комментариев
            await self._clear_comments_cache(target_type, target_id)
            
            # Возвращаем данные комментария с информацией об авторе
            return await self._build_comment_data(comment, author_data)
            
        except Exception as e:
            logger.error(f"Ошибка создания комментария от пользователя {author_id}: {e}")
            return None
    
    async def get_comments_for_target(
        self,
        target_type: str,
        target_id: int,
        comment_type: Optional[CommentType] = None,
        viewer_user_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Получение комментариев для объекта с информацией об авторах
        
        Args:
            target_type: Тип объекта
            target_id: ID объекта
            comment_type: Тип комментария (опционально)
            viewer_user_id: ID пользователя, который просматривает комментарии
            limit: Максимальное количество комментариев
            offset: Смещение для пагинации
            
        Returns:
            Список комментариев с данными авторов
        """
        try:
            # Проверяем кэш
            cache_key = f"comments:{target_type}:{target_id}:{comment_type or 'all'}"
            cached_comments = await cache_service.get(cache_key)
            if cached_comments and offset == 0:
                logger.debug(f"Комментарии для {target_type}:{target_id} получены из кэша")
                return cached_comments[:limit]
            
            # Получаем комментарии из БД
            comments = await self.comment_repo.get_comments_for_target(
                target_type=target_type,
                target_id=target_id,
                comment_type=comment_type,
                status=CommentStatus.ACTIVE,
                limit=limit,
                offset=offset
            )
            
            # Собираем данные комментариев с информацией об авторах
            result = []
            for comment in comments:
                # Для административных заметок проверяем права доступа
                if (comment.comment_type == CommentType.ADMIN_NOTE and 
                    not await self._can_view_admin_notes(viewer_user_id)):
                    continue
                
                # Получаем данные автора (если комментарий не анонимный)
                author_data = None
                if not comment.is_anonymous:
                    author_data = await auth_client.get_user_by_id(comment.author_id)
                
                comment_data = await self._build_comment_data(comment, author_data)
                result.append(comment_data)
            
            # Кэшируем результат (только для первой страницы)
            if offset == 0:
                await cache_service.set(
                    cache_key, 
                    result, 
                    settings.cache_comments_ttl
                )
            
            logger.debug(f"Получено {len(result)} комментариев для {target_type}:{target_id}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения комментариев для {target_type}:{target_id}: {e}")
            return []
    
    async def get_teacher_reviews(
        self,
        teacher_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Получение отзывов о преподавателе с статистикой
        
        Args:
            teacher_id: ID преподавателя
            limit: Максимальное количество отзывов
            offset: Смещение для пагинации
            
        Returns:
            Словарь с отзывами и статистикой рейтинга
        """
        try:
            # Проверяем кэш
            cache_key = f"teacher_reviews_full:{teacher_id}"
            cached_data = await cache_service.get(cache_key)
            if cached_data and offset == 0:
                logger.debug(f"Отзывы о преподавателе {teacher_id} получены из кэша")
                return cached_data
            
            # Получаем отзывы
            reviews = await self.comment_repo.get_public_reviews_for_teacher(
                teacher_id=teacher_id,
                limit=limit,
                offset=offset
            )
            
            # Получаем статистику рейтинга
            rating_stats = await self.comment_repo.get_teacher_rating_stats(teacher_id)
            
            # Собираем данные отзывов с авторами
            reviews_data = []
            for review in reviews:
                author_data = await auth_client.get_user_by_id(review.author_id)
                review_data = await self._build_comment_data(review, author_data)
                reviews_data.append(review_data)
            
            result = {
                "teacher_id": teacher_id,
                "rating_stats": rating_stats,
                "reviews": reviews_data,
                "total_reviews": rating_stats.get("total_reviews", 0)
            }
            
            # Кэшируем результат (только для первой страницы)
            if offset == 0:
                await cache_service.set(
                    cache_key, 
                    result, 
                    settings.cache_comments_ttl
                )
            
            logger.debug(f"Получено {len(reviews_data)} отзывов о преподавателе {teacher_id}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения отзывов о преподавателе {teacher_id}: {e}")
            return {"teacher_id": teacher_id, "rating_stats": {}, "reviews": [], "total_reviews": 0}
    
    async def update_comment(
        self,
        comment_id: int,
        author_id: int,
        content: Optional[str] = None,
        title: Optional[str] = None,
        rating: Optional[int] = None,
        edit_reason: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обновление комментария
        
        Args:
            comment_id: ID комментария
            author_id: ID автора (для проверки прав)
            content: Новый текст комментария
            title: Новый заголовок
            rating: Новый рейтинг
            edit_reason: Причина редактирования
            
        Returns:
            Обновленный комментарий или None
        """
        try:
            # Получаем существующий комментарий
            comment = await self.comment_repo.get_by_id(comment_id)
            if not comment:
                logger.warning(f"Комментарий {comment_id} не найден")
                return None
            
            # Проверяем права на редактирование
            if comment.author_id != author_id:
                logger.warning(f"Пользователь {author_id} пытается редактировать чужой комментарий {comment_id}")
                return None
            
            # Валидация нового контента
            if content and len(content.strip()) < 10:
                logger.warning(f"Попытка обновить комментарий {comment_id} слишком коротким текстом")
                return None
            
            if content and len(content) > settings.max_comment_length:
                logger.warning(f"Попытка обновить комментарий {comment_id} слишком длинным текстом")
                return None
            
            # Обновляем комментарий
            updated_comment = await self.comment_repo.update_comment(
                comment_id=comment_id,
                content=content,
                title=title,
                rating=rating,
                edit_reason=edit_reason
            )
            
            if updated_comment:
                # Логируем активность
                await self.activity_repo.log_activity(
                    user_id=author_id,
                    activity_type=ActivityType.COMMENT_UPDATED,
                    title="Комментарий отредактирован",
                    description=f"Отредактирован комментарий {comment_id}",
                    level=ActivityLevel.LOW,
                    target_type="comment",
                    target_id=comment_id,
                    activity_data={
                        "edit_reason": edit_reason,
                        "updated_fields": [k for k, v in {"content": content, "title": title, "rating": rating}.items() if v is not None]
                    }
                )
                
                # Очищаем кэш
                await self._clear_comments_cache(comment.target_type, comment.target_id)
                
                # Получаем данные автора и возвращаем обновленный комментарий
                author_data = await auth_client.get_user_by_id(author_id)
                return await self._build_comment_data(updated_comment, author_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка обновления комментария {comment_id}: {e}")
            return None
    
    async def moderate_comment(
        self,
        comment_id: int,
        moderator_id: int,
        action: str,
        reason: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Модерация комментария администратором
        
        Args:
            comment_id: ID комментария
            moderator_id: ID модератора
            action: Действие (hide, restore, delete, verify)
            reason: Причина модерации
            
        Returns:
            Обновленный комментарий или None
        """
        try:
            # Проверяем права модератора
            moderator_data = await auth_client.get_user_by_id(moderator_id)
            if not moderator_data or moderator_data.get("role", {}).get("name") not in ["admin", "moderator"]:
                logger.warning(f"Пользователь {moderator_id} пытается модерировать без прав")
                return None
            
            # Получаем комментарий
            comment = await self.comment_repo.get_by_id(comment_id)
            if not comment:
                logger.warning(f"Комментарий {comment_id} не найден для модерации")
                return None
            
            # Выполняем модерацию
            moderated_comment = await self.comment_repo.moderate_comment(
                comment_id=comment_id,
                action=action,
                moderator_id=moderator_id
            )
            
            if moderated_comment:
                # Логируем активность модерации
                await self.activity_repo.log_activity(
                    user_id=moderator_id,
                    activity_type=ActivityType.COMMENT_UPDATED,
                    title=f"Модерация комментария: {action}",
                    description=f"Выполнена модерация комментария {comment_id}",
                    level=ActivityLevel.HIGH,
                    target_type="comment",
                    target_id=comment_id,
                    activity_data={
                        "moderation_action": action,
                        "reason": reason,
                        "original_author_id": comment.author_id
                    }
                )
                
                # Очищаем кэш
                await self._clear_comments_cache(comment.target_type, comment.target_id)
                
                logger.info(f"Модерация комментария {comment_id}: {action} модератором {moderator_id}")
                
                # Возвращаем обновленный комментарий
                author_data = await auth_client.get_user_by_id(comment.author_id)
                return await self._build_comment_data(moderated_comment, author_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка модерации комментария {comment_id}: {e}")
            return None
    
    async def get_user_comments(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Получение комментариев пользователя
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество комментариев
            offset: Смещение для пагинации
            
        Returns:
            Список комментариев пользователя
        """
        try:
            comments = await self.comment_repo.get_user_comments(
                author_id=user_id,
                status=CommentStatus.ACTIVE,
                limit=limit,
                offset=offset
            )
            
            result = []
            for comment in comments:
                # Для собственных комментариев показываем полную информацию
                comment_data = comment.to_dict()
                comment_data["target_info"] = {
                    "type": comment.target_type,
                    "id": comment.target_id
                }
                result.append(comment_data)
            
            logger.debug(f"Получено {len(result)} комментариев пользователя {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения комментариев пользователя {user_id}: {e}")
            return []
    
    # Приватные методы
    
    async def _build_comment_data(
        self, 
        comment: Comment, 
        author_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Сборка данных комментария с информацией об авторе"""
        
        comment_data = comment.to_dict_public()
        
        # Добавляем информацию об авторе
        if author_data and not comment.is_anonymous:
            comment_data["author"] = {
                "id": author_data["id"],
                "first_name": author_data.get("first_name", ""),
                "last_name": author_data.get("last_name", ""),
                "role": author_data.get("role", {}).get("name", ""),
                "is_verified": author_data.get("is_verified", False)
            }
        else:
            comment_data["author"] = {
                "id": None,
                "first_name": "Аноним",
                "last_name": "",
                "role": "",
                "is_verified": False
            }
        
        return comment_data
    
    async def _can_view_admin_notes(self, user_id: Optional[int]) -> bool:
        """Проверка прав на просмотр административных заметок"""
        if not user_id:
            return False
        
        try:
            user_data = await auth_client.get_user_by_id(user_id)
            if not user_data:
                return False
            
            role = user_data.get("role", {}).get("name", "")
            return role in ["admin", "moderator"]
            
        except Exception as e:
            logger.error(f"Ошибка проверки прав на админ заметки для пользователя {user_id}: {e}")
            return False
    
    async def _clear_comments_cache(self, target_type: str, target_id: int):
        """Очистка кэша комментариев"""
        try:
            patterns = [
                f"comments:{target_type}:{target_id}:*",
                f"teacher_reviews_full:{target_id}" if target_type == "teacher" else None
            ]
            
            for pattern in patterns:
                if pattern:
                    await cache_service.clear_pattern(pattern)
            
            logger.debug(f"Очищен кэш комментариев для {target_type}:{target_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки кэша комментариев {target_type}:{target_id}: {e}")