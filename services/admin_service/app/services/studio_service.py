"""
Studio Service.

Все операции записи (create, update, delete) сопровождаются
записью события в outbox для асинхронной публикации в RabbitMQ
(exchange 'admin_events'). Запись в outbox делается в той же
транзакции, что и бизнес-данные - это гарантирует атомарность:
либо и студия, и событие сохранены, либо ничего.

Семантика delete - soft-delete (is_active=False), чтобы не нарушать
ссылочную целостность с lessons и patterns в Schedule Service.
"""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.studio_repository import StudioRepository
from app.models.studio import Studio
from app.messaging.outbox import (
    record_studio_created,
    record_studio_updated,
    record_studio_deactivated,
)

logger = logging.getLogger(__name__)


class StudioService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StudioRepository(db)
    
    async def get_all_studios(self, include_inactive: bool = False) -> List[Studio]:
        if include_inactive:
            return await self.repo.get_all()
        return await self.repo.get_active_studios()
    
    async def get_studios_by_ids(
        self,
        studio_ids: List[int],
        include_inactive: bool = False,
    ):
        """Получить студии по списку ID."""
        if not studio_ids:
            return []
        
        stmt = select(Studio).where(Studio.id.in_(studio_ids))
        if not include_inactive:
            stmt = stmt.where(Studio.is_active.is_(True))
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_studio(self, studio_id: int) -> Optional[Studio]:
        return await self.repo.get_by_id(studio_id)
    
    async def create_studio(self, **data) -> Studio:
        """
        Создать студию и записать событие 'studio.created' в outbox.
        
        Запись в outbox идёт в той же транзакции что и создание студии:
        commit делает get_async_session в конце dependency.
        """
        studio = await self.repo.create(**data)
        await record_studio_created(self.db, studio)
        return studio
    
    async def update_studio(self, studio_id: int, **data) -> Optional[Studio]:
        """
        Обновить студию и записать событие 'studio.updated' в outbox.
        
        Если студия не найдена - событие не записывается.
        """
        studio = await self.repo.update(studio_id, **data)
        if studio is None:
            return None
        await record_studio_updated(self.db, studio)
        return studio
    
    async def delete_studio(self, studio_id: int) -> bool:
        """
        Soft-delete студии: ставит is_active=False и публикует
        событие 'studio.deactivated'.
        
        Hard-delete не используется для сохранения ссылочной целостности
        с lessons/patterns в Schedule Service.
        """
        studio = await self.repo.get_by_id(studio_id)
        if studio is None:
            return False
        
        # Если студия уже деактивирована - не делаем повторных событий,
        # чтобы избежать нагрузки на consumer'ов.
        if studio.is_active is False:
            logger.info(
                "Studio already deactivated, skipping: studio_id=%s",
                studio_id,
            )
            return True
        
        studio.is_active = False
        await self.db.flush()
        
        await record_studio_deactivated(self.db, studio_id)
        return True