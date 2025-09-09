"""
Репозиторий для работы с активностью пользователей
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc, delete
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import logging

from app.models.activity import UserActivity, ActivityType, ActivityLevel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ActivityRepository(BaseRepository[UserActivity]):
    """Репозиторий для работы с активностью пользователей"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(UserActivity, db)
    
    async def log_activity(
        self,
        user_id: int,
        activity_type: ActivityType,
        title: str,
        description: Optional[str] = None,
        level: ActivityLevel = ActivityLevel.LOW,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        activity_data: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> Optional[UserActivity]:
        """
        Логирование активности пользователя
        
        Args:
            user_id: ID пользователя
            activity_type: Тип активности
            title: Краткое описание
            description: Подробное описание
            level: Уровень важности
            target_type: Тип связанного объекта
            target_id: ID связанного объекта
            activity_data: Дополнительные данные
            ip_address: IP адрес
            user_agent: User-Agent
            session_id: ID сессии
            success: Успешность операции
            error_message: Сообщение об ошибке
            
        Returns:
            Созданная запись активности или None
        """
        try:
            activity = UserActivity.create_activity(
                user_id=user_id,
                activity_type=activity_type,
                title=title,
                description=description,
                level=level,
                target_type=target_type,
                target_id=target_id,
                activity_data=activity_data,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
                success=success,
                error_message=error_message
            )
            
            self.db.add(activity)
            await self.db.commit()
            await self.db.refresh(activity)
            
            logger.debug(f"Залогирована активность {activity_type} пользователя {user_id}")
            return activity
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка логирования активности пользователя {user_id}: {e}")
            return None
    
    async def get_user_activities(
        self,
        user_id: int,
        activity_type: Optional[ActivityType] = None,
        level: Optional[ActivityLevel] = None,
        success_only: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[UserActivity]:
        """
        Получение активности пользователя
        
        Args:
            user_id: ID пользователя
            activity_type: Тип активности (опционально)
            level: Уровень важности (опционально)
            success_only: Только успешные операции
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            
        Returns:
            Список активности пользователя
        """
        try:
            query = select(UserActivity).where(UserActivity.user_id == user_id)
            
            # Фильтры
            if activity_type:
                query = query.where(UserActivity.activity_type == activity_type)
            if level:
                query = query.where(UserActivity.level == level)
            if success_only:
                query = query.where(UserActivity.success == True)
            
            # Сортировка по дате создания (новые сначала)
            query = query.order_by(desc(UserActivity.created_at))
            
            # Пагинация
            query = query.limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            activities = result.scalars().all()
            
            logger.debug(f"Получено {len(activities)} записей активности пользователя {user_id}")
            return list(activities)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения активности пользователя {user_id}: {e}")
            return []
    
    async def get_recent_activities(
        self,
        user_id: int,
        days: int = 7,
        limit: int = 20
    ) -> List[UserActivity]:
        """
        Получение недавней активности пользователя
        
        Args:
            user_id: ID пользователя
            days: Количество дней назад
            limit: Максимальное количество записей
            
        Returns:
            Список недавней активности
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = await self.db.execute(
                select(UserActivity)
                .where(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.created_at >= cutoff_date,
                        UserActivity.success == True
                    )
                )
                .order_by(desc(UserActivity.created_at))
                .limit(limit)
            )
            activities = result.scalars().all()
            
            logger.debug(f"Получено {len(activities)} недавних активностей пользователя {user_id}")
            return list(activities)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения недавней активности пользователя {user_id}: {e}")
            return []
    
    async def get_important_activities(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[UserActivity]:
        """
        Получение важной активности пользователя
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество записей
            
        Returns:
            Список важной активности
        """
        try:
            result = await self.db.execute(
                select(UserActivity)
                .where(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.level.in_([ActivityLevel.HIGH, ActivityLevel.SYSTEM]),
                        UserActivity.success == True
                    )
                )
                .order_by(desc(UserActivity.created_at))
                .limit(limit)
            )
            activities = result.scalars().all()
            
            logger.debug(f"Получено {len(activities)} важных активностей пользователя {user_id}")
            return list(activities)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения важной активности пользователя {user_id}: {e}")
            return []
    
    async def get_failed_activities(
        self,
        user_id: int,
        days: int = 30,
        limit: int = 20
    ) -> List[UserActivity]:
        """
        Получение неудачных операций пользователя
        
        Args:
            user_id: ID пользователя
            days: Количество дней назад
            limit: Максимальное количество записей
            
        Returns:
            Список неудачных операций
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = await self.db.execute(
                select(UserActivity)
                .where(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.created_at >= cutoff_date,
                        UserActivity.success == False
                    )
                )
                .order_by(desc(UserActivity.created_at))
                .limit(limit)
            )
            activities = result.scalars().all()
            
            logger.debug(f"Получено {len(activities)} неудачных операций пользователя {user_id}")
            return list(activities)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения неудачных операций пользователя {user_id}: {e}")
            return []
    
    async def get_activity_statistics(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Получение статистики активности пользователя
        
        Args:
            user_id: ID пользователя
            days: Период для анализа (дней)
            
        Returns:
            Словарь со статистикой активности
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Общая статистика
            total_result = await self.db.execute(
                select(
                    func.count(UserActivity.id).label("total_activities"),
                    func.count(UserActivity.id).filter(UserActivity.success == True).label("successful_activities"),
                    func.count(UserActivity.id).filter(UserActivity.success == False).label("failed_activities")
                )
                .where(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.created_at >= cutoff_date
                    )
                )
            )
            total_stats = total_result.first()
            
            # Статистика по типам активности
            type_result = await self.db.execute(
                select(
                    UserActivity.activity_type,
                    func.count(UserActivity.id).label("count")
                )
                .where(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.created_at >= cutoff_date,
                        UserActivity.success == True
                    )
                )
                .group_by(UserActivity.activity_type)
            )
            
            activity_by_type = {}
            for row in type_result:
                activity_by_type[row.activity_type.value] = row.count
            
            # Статистика по уровням важности
            level_result = await self.db.execute(
                select(
                    UserActivity.level,
                    func.count(UserActivity.id).label("count")
                )
                .where(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.created_at >= cutoff_date,
                        UserActivity.success == True
                    )
                )
                .group_by(UserActivity.level)
            )
            
            activity_by_level = {}
            for row in level_result:
                activity_by_level[row.level.value] = row.count
            
            return {
                "period_days": days,
                "total_activities": total_stats.total_activities or 0,
                "successful_activities": total_stats.successful_activities or 0,
                "failed_activities": total_stats.failed_activities or 0,
                "success_rate": (
                    (total_stats.successful_activities / total_stats.total_activities * 100)
                    if total_stats.total_activities > 0 else 0.0
                ),
                "activity_by_type": activity_by_type,
                "activity_by_level": activity_by_level
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения статистики активности пользователя {user_id}: {e}")
            return {
                "period_days": days,
                "total_activities": 0,
                "successful_activities": 0,
                "failed_activities": 0,
                "success_rate": 0.0,
                "activity_by_type": {},
                "activity_by_level": {}
            }
    
    async def get_system_activities(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserActivity]:
        """
        Получение системной активности для администраторов
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            
        Returns:
            Список системной активности
        """
        try:
            result = await self.db.execute(
                select(UserActivity)
                .where(UserActivity.level == ActivityLevel.SYSTEM)
                .order_by(desc(UserActivity.created_at))
                .limit(limit)
                .offset(offset)
            )
            activities = result.scalars().all()
            
            logger.debug(f"Получено {len(activities)} записей системной активности")
            return list(activities)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения системной активности: {e}")
            return []
    
    async def cleanup_old_activities(self, days: int = 365) -> int:
        """
        Очистка старых записей активности
        
        Args:
            days: Количество дней для хранения записей
            
        Returns:
            Количество удаленных записей
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = await self.db.execute(
                select(func.count(UserActivity.id))
                .where(
                    and_(
                        UserActivity.created_at < cutoff_date,
                        UserActivity.level != ActivityLevel.SYSTEM  # Не удаляем системные записи
                    )
                )
            )
            count_to_delete = result.scalar()
            
            if count_to_delete > 0:
                delete_result = await self.db.execute(
                    UserActivity.__table__.delete()
                    .where(
                        and_(
                            UserActivity.created_at < cutoff_date,
                            UserActivity.level != ActivityLevel.SYSTEM
                        )
                    )
                )
                await self.db.commit()
                
                deleted_count = delete_result.rowcount
                logger.info(f"Удалено {deleted_count} старых записей активности (старше {days} дней)")
                return deleted_count
            else:
                logger.debug("Нет старых записей активности для удаления")
                return 0
                
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка очистки старых записей активности: {e}")
            return 0