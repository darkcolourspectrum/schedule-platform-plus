"""Репозиторий для processed_events (идемпотентность consumer'ов)."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processed_event import ProcessedEvent


class ProcessedEventRepository:
    """
    Доступ к журналу обработанных событий.

    Не коммитит: проверка и запись идемпотентности - часть транзакции
    обработчика события (вместе с бизнес-изменениями).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_processed(self, event_id: UUID) -> bool:
        result = await self.db.execute(
            select(ProcessedEvent.event_id).where(
                ProcessedEvent.event_id == event_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_processed(self, event_id: UUID, event_type: str) -> None:
        """Записать event_id. Не коммитит."""
        self.db.add(ProcessedEvent(event_id=event_id, event_type=event_type))
