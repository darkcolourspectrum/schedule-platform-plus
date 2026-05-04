"""
Classroom Service.

Все операции записи (create, update, delete) сопровождаются
записью события в outbox для асинхронной публикации в RabbitMQ
(exchange 'admin_events').

Семантика delete - soft-delete (is_active=False).
"""

import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.classroom_repository import ClassroomRepository
from app.models.classroom import Classroom
from app.messaging.outbox import (
    record_classroom_created,
    record_classroom_updated,
    record_classroom_deactivated,
)

logger = logging.getLogger(__name__)


class ClassroomService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ClassroomRepository(db)
    
    async def get_studio_classrooms(self, studio_id: int) -> List[Classroom]:
        return await self.repo.get_by_studio(studio_id)
    
    async def get_classroom(self, classroom_id: int) -> Optional[Classroom]:
        return await self.repo.get_by_id(classroom_id)
    
    async def create_classroom(self, studio_id: int, **data) -> Classroom:
        """
        Создать кабинет и записать событие 'classroom.created' в outbox.
        """
        classroom = await self.repo.create(studio_id=studio_id, **data)
        await record_classroom_created(self.db, classroom)
        return classroom
    
    async def update_classroom(
        self,
        classroom_id: int,
        **data,
    ) -> Optional[Classroom]:
        """
        Обновить кабинет и записать событие 'classroom.updated' в outbox.
        """
        classroom = await self.repo.update(classroom_id, **data)
        if classroom is None:
            return None
        await record_classroom_updated(self.db, classroom)
        return classroom
    
    async def delete_classroom(self, classroom_id: int) -> bool:
        """
        Soft-delete кабинета: ставит is_active=False и публикует
        событие 'classroom.deactivated'.
        """
        classroom = await self.repo.get_by_id(classroom_id)
        if classroom is None:
            return False
        
        if classroom.is_active is False:
            logger.info(
                "Classroom already deactivated, skipping: classroom_id=%s",
                classroom_id,
            )
            return True
        
        classroom.is_active = False
        await self.db.flush()
        
        await record_classroom_deactivated(self.db, classroom_id)
        return True