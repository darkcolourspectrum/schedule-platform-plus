"""
Репозиторий для работы с комментариями и отзывами
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import logging

from app.models.comment import Comment, CommentType, CommentStatus
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class CommentRepository(BaseRepository[Comment]):
    """Репозиторий для работы с комментариями"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Comment, db)
    
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
        **kwargs
    ) -> Optional[Comment]:
        """
        Создание нового комментария
        
        Args:
            author_id: ID автора комментария
            target_type: Тип объекта (teacher, student, lesson, profile)
            target_id: ID объекта
            comment_type: Тип комментария
            content: Текст комментария
            title: Заголовок комментария
            rating: Рейтинг (для отзывов)
            is_anonymous: Анонимный комментарий
            **kwargs: Дополнительные параметры
            
        Returns:
            Созданный комментарий или None
        """
        try:
            comment_data = {
                "author_id": author_id,
                "target_type": target_type,
                "target_id": target_id,
                "comment_type": comment_type,
                "content": content,
                "title": title,
                "rating": rating,
                "is_anonymous": is_anonymous,
                "status": CommentStatus.ACTIVE,
                **kwargs
            }
            
            comment = await self.create(**comment_data)
            
            if comment:
                logger.info(f"Создан комментарий {comment.id} от пользователя {author_id}")
            
            return comment
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка создания комментария: {e}")
            return None
    
    async def get_comments_for_target(
        self,
        target_type: str,
        target_id: int,
        comment_type: Optional[CommentType] = None,
        status: CommentStatus = CommentStatus.ACTIVE,
        limit: int = 50,
        offset: int = 0
    ) -> List[Comment]:
        """
        Получение комментариев для объекта
        
        Args:
            target_type: Тип объекта
            target_id: ID объекта
            comment_type: Тип комментария (опционально)
            status: Статус комментариев
            limit: Максимальное количество комментариев
            offset: Смещение для пагинации
            
        Returns:
            Список комментариев
        """
        try:
            query = select(Comment).where(
                and_(
                    Comment.target_type == target_type,
                    Comment.target_id == target_id,
                    Comment.status == status
                )
            )
            
            # Фильтр по типу комментария
            if comment_type:
                query = query.where(Comment.comment_type == comment_type)
            
            # Сортировка по дате создания (новые сначала)
            query = query.order_by(desc(Comment.created_at))
            
            # Пагинация
            query = query.limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            comments = result.scalars().all()
            
            logger.debug(f"Получено {len(comments)} комментариев для {target_type}:{target_id}")
            return list(comments)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения комментариев для {target_type}:{target_id}: {e}")
            return []
    
    async def get_user_comments(
        self,
        author_id: int,
        status: Optional[CommentStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Comment]:
        """
        Получение комментариев пользователя
        
        Args:
            author_id: ID автора
            status: Статус комментариев (опционально)
            limit: Максимальное количество комментариев
            offset: Смещение для пагинации
            
        Returns:
            Список комментариев пользователя
        """
        try:
            query = select(Comment).where(Comment.author_id == author_id)
            
            # Фильтр по статусу
            if status:
                query = query.where(Comment.status == status)
            
            # Сортировка по дате создания (новые сначала)
            query = query.order_by(desc(Comment.created_at))
            
            # Пагинация
            query = query.limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            comments = result.scalars().all()
            
            logger.debug(f"Получено {len(comments)} комментариев пользователя {author_id}")
            return list(comments)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения комментариев пользователя {author_id}: {e}")
            return []
    
    async def get_public_reviews_for_teacher(
        self,
        teacher_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[Comment]:
        """
        Получение публичных отзывов о преподавателе
        
        Args:
            teacher_id: ID преподавателя
            limit: Максимальное количество отзывов
            offset: Смещение для пагинации
            
        Returns:
            Список публичных отзывов
        """
        try:
            result = await self.db.execute(
                select(Comment)
                .where(
                    and_(
                        Comment.target_type == "teacher",
                        Comment.target_id == teacher_id,
                        Comment.comment_type == CommentType.PUBLIC_REVIEW,
                        Comment.status == CommentStatus.ACTIVE
                    )
                )
                .order_by(desc(Comment.created_at))
                .limit(limit)
                .offset(offset)
            )
            reviews = result.scalars().all()
            
            logger.debug(f"Получено {len(reviews)} публичных отзывов о преподавателе {teacher_id}")
            return list(reviews)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения отзывов о преподавателе {teacher_id}: {e}")
            return []
    
    async def get_admin_notes_for_user(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[Comment]:
        """
        Получение административных заметок о пользователе
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество заметок
            
        Returns:
            Список административных заметок
        """
        try:
            result = await self.db.execute(
                select(Comment)
                .where(
                    and_(
                        Comment.target_type.in_(["student", "teacher", "profile"]),
                        Comment.target_id == user_id,
                        Comment.comment_type == CommentType.ADMIN_NOTE,
                        Comment.status == CommentStatus.ACTIVE
                    )
                )
                .order_by(desc(Comment.created_at))
                .limit(limit)
            )
            notes = result.scalars().all()
            
            logger.debug(f"Получено {len(notes)} административных заметок о пользователе {user_id}")
            return list(notes)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения админ заметок о пользователе {user_id}: {e}")
            return []
    
    async def update_comment(
        self,
        comment_id: int,
        content: Optional[str] = None,
        title: Optional[str] = None,
        rating: Optional[int] = None,
        edit_reason: Optional[str] = None
    ) -> Optional[Comment]:
        """
        Обновление комментария
        
        Args:
            comment_id: ID комментария
            content: Новый текст комментария
            title: Новый заголовок
            rating: Новый рейтинг
            edit_reason: Причина редактирования
            
        Returns:
            Обновленный комментарий или None
        """
        try:
            comment = await self.get_by_id(comment_id)
            if not comment:
                logger.warning(f"Комментарий {comment_id} не найден для обновления")
                return None
            
            # Проверяем возможность редактирования
            if not comment.is_editable:
                logger.warning(f"Комментарий {comment_id} нельзя редактировать (слишком старый)")
                return None
            
            # Обновляем поля
            if content is not None:
                comment.content = content
            if title is not None:
                comment.title = title
            if rating is not None:
                comment.rating = rating
            
            # Отмечаем как отредактированный
            comment.mark_as_edited(edit_reason)
            
            await self.db.commit()
            await self.db.refresh(comment)
            
            logger.debug(f"Обновлен комментарий {comment_id}")
            return comment
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления комментария {comment_id}: {e}")
            return None
    
    async def moderate_comment(
        self,
        comment_id: int,
        action: str,
        moderator_id: int
    ) -> Optional[Comment]:
        """
        Модерация комментария
        
        Args:
            comment_id: ID комментария
            action: Действие (hide, restore, delete, verify)
            moderator_id: ID модератора
            
        Returns:
            Обновленный комментарий или None
        """
        try:
            comment = await self.get_by_id(comment_id)
            if not comment:
                logger.warning(f"Комментарий {comment_id} не найден для модерации")
                return None
            
            # Применяем действие модерации
            if action == "hide":
                comment.hide(moderator_id)
            elif action == "restore":
                comment.restore(moderator_id)
            elif action == "delete":
                comment.soft_delete(moderator_id)
            elif action == "verify":
                comment.verify(moderator_id)
            else:
                logger.warning(f"Неизвестное действие модерации: {action}")
                return None
            
            await self.db.commit()
            await self.db.refresh(comment)
            
            logger.info(f"Выполнена модерация комментария {comment_id}: {action} модератором {moderator_id}")
            return comment
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка модерации комментария {comment_id}: {e}")
            return None
    
    async def get_teacher_rating_stats(self, teacher_id: int) -> Dict[str, Any]:
        """
        Получение статистики рейтинга преподавателя
        
        Args:
            teacher_id: ID преподавателя
            
        Returns:
            Словарь со статистикой рейтинга
        """
        try:
            # Запрос статистики рейтинга
            result = await self.db.execute(
                select(
                    func.count(Comment.id).label("total_reviews"),
                    func.avg(Comment.rating).label("average_rating"),
                    func.min(Comment.rating).label("min_rating"),
                    func.max(Comment.rating).label("max_rating")
                )
                .where(
                    and_(
                        Comment.target_type == "teacher",
                        Comment.target_id == teacher_id,
                        Comment.comment_type == CommentType.PUBLIC_REVIEW,
                        Comment.status == CommentStatus.ACTIVE,
                        Comment.rating.isnot(None)
                    )
                )
            )
            stats = result.first()
            
            if not stats or stats.total_reviews == 0:
                return {
                    "total_reviews": 0,
                    "average_rating": 0.0,
                    "min_rating": 0,
                    "max_rating": 0,
                    "rating_distribution": {}
                }
            
            # Получаем распределение рейтингов
            rating_result = await self.db.execute(
                select(
                    Comment.rating,
                    func.count(Comment.id).label("count")
                )
                .where(
                    and_(
                        Comment.target_type == "teacher",
                        Comment.target_id == teacher_id,
                        Comment.comment_type == CommentType.PUBLIC_REVIEW,
                        Comment.status == CommentStatus.ACTIVE,
                        Comment.rating.isnot(None)
                    )
                )
                .group_by(Comment.rating)
            )
            
            rating_distribution = {}
            for row in rating_result:
                rating_distribution[str(row.rating)] = row.count
            
            return {
                "total_reviews": stats.total_reviews,
                "average_rating": float(stats.average_rating) if stats.average_rating else 0.0,
                "min_rating": stats.min_rating,
                "max_rating": stats.max_rating,
                "rating_distribution": rating_distribution
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения статистики рейтинга преподавателя {teacher_id}: {e}")
            return {
                "total_reviews": 0,
                "average_rating": 0.0,
                "min_rating": 0,
                "max_rating": 0,
                "rating_distribution": {}
            }
    
    async def count_comments_for_target(
        self,
        target_type: str,
        target_id: int,
        comment_type: Optional[CommentType] = None,
        status: CommentStatus = CommentStatus.ACTIVE
    ) -> int:
        """
        Подсчет количества комментариев для объекта
        
        Args:
            target_type: Тип объекта
            target_id: ID объекта
            comment_type: Тип комментария (опционально)
            status: Статус комментариев
            
        Returns:
            Количество комментариев
        """
        try:
            query = select(func.count(Comment.id)).where(
                and_(
                    Comment.target_type == target_type,
                    Comment.target_id == target_id,
                    Comment.status == status
                )
            )
            
            # Фильтр по типу комментария
            if comment_type:
                query = query.where(Comment.comment_type == comment_type)
            
            result = await self.db.execute(query)
            count = result.scalar()
            
            return count or 0
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка подсчета комментариев для {target_type}:{target_id}: {e}")
            return 0