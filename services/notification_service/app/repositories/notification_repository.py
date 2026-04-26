"""Notification repository"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    """Репозиторий для работы с уведомлениями"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(
        self,
        user_id: int,
        type: str,
        title: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """Создать уведомление"""
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            payload=payload,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification
    
    async def get_by_id(self, notification_id: int) -> Optional[Notification]:
        """Получить уведомление по ID"""
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[Notification]:
        """Получить уведомления пользователя"""
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def count_user_notifications(
        self,
        user_id: int,
        unread_only: bool = False,
    ) -> int:
        """Подсчитать уведомления пользователя"""
        stmt = select(func.count(Notification.id)).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        result = await self.db.execute(stmt)
        return result.scalar_one()
    
    async def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """
        Пометить уведомление как прочитанное.
        Возвращает True если пометили, False если такого уведомления нет
        или оно принадлежит другому пользователю.
        """
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Пометить все уведомления пользователя как прочитанные. Вернуть число обновлённых."""
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount