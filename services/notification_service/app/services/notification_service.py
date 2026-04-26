"""Notification service - business logic"""
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.notification_repository import NotificationRepository
from app.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис для работы с уведомлениями"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)
    
    async def create_notification(
        self,
        user_id: int,
        type: str,
        title: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """Создать уведомление для пользователя"""
        notification = await self.repo.create(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            payload=payload,
        )
        logger.info(
            "Notification created: id=%s user_id=%s type=%s",
            notification.id, user_id, type,
        )
        return notification
    
    async def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> Dict[str, Any]:
        """Получить уведомления пользователя со счётчиками"""
        notifications = await self.repo.get_user_notifications(
            user_id=user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )
        total = await self.repo.count_user_notifications(user_id, unread_only=False)
        unread_count = await self.repo.count_user_notifications(user_id, unread_only=True)
        return {
            "notifications": notifications,
            "total": total,
            "unread_count": unread_count,
        }
    
    async def get_unread_count(self, user_id: int) -> int:
        """Получить количество непрочитанных"""
        return await self.repo.count_user_notifications(user_id, unread_only=True)
    
    async def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Пометить как прочитанное (только если принадлежит пользователю)"""
        return await self.repo.mark_as_read(notification_id, user_id)
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Пометить все как прочитанные. Вернуть число обновлённых."""
        return await self.repo.mark_all_as_read(user_id)