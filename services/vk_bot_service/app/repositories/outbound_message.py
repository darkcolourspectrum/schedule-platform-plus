"""Репозиторий для outbound_messages (журнал и очередь исходящих VK-сообщений)."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.outbound_message import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_UNDELIVERABLE,
    OutboundMessage,
)

logger = logging.getLogger(__name__)


class OutboundMessageRepository:
    """
    Доступ к очереди исходящих сообщений.

    create() не коммитит (часть транзакции consumer'а вместе с
    processed_events). Методы смены статуса и выборки очереди коммитят
    сами - их вызывает retry-воркер вне какой-либо общей транзакции.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        vk_id: int,
        message: str,
        user_id: Optional[int] = None,
        source_event_type: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> OutboundMessage:
        """
        Поставить сообщение в очередь на отправку (status=pending).

        Не коммитит: вызывается из обработчика события расписания в одной
        транзакции с записью в processed_events.
        """
        msg = OutboundMessage(
            vk_id=vk_id,
            user_id=user_id,
            message=message,
            status=STATUS_PENDING,
            attempts=0,
            source_event_type=source_event_type,
            source_event_id=source_event_id,
        )
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def fetch_retryable(self, limit: int) -> List[OutboundMessage]:
        """
        Выбрать сообщения для (повторной) отправки: pending или failed,
        не исчерпавшие лимит попыток. FOR UPDATE SKIP LOCKED - на случай
        нескольких реплик воркера.
        """
        result = await self.db.execute(
            select(OutboundMessage)
            .where(
                OutboundMessage.status.in_([STATUS_PENDING, STATUS_FAILED]),
                OutboundMessage.attempts < settings.outbound_max_attempts,
            )
            .order_by(OutboundMessage.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def mark_sent(self, msg: OutboundMessage) -> None:
        """Пометить успешно отправленным."""
        msg.status = STATUS_SENT
        msg.attempts += 1
        msg.sent_at = datetime.now(timezone.utc)
        msg.last_error = None
        await self.db.commit()

    async def mark_failed(self, msg: OutboundMessage, error: str) -> None:
        """
        Пометить неудачной транзиентной попыткой. Останется в очереди и
        будет повторено, пока attempts < max_attempts; при достижении
        лимита воркер больше не выберет её (fetch_retryable отфильтрует).
        """
        msg.status = STATUS_FAILED
        msg.attempts += 1
        msg.last_error = error[:2000]
        await self.db.commit()

    async def mark_undeliverable(self, msg: OutboundMessage, error: str) -> None:
        """
        Пометить перманентно недоставляемым (VK код 901/902 и т.п.).
        Повторов не будет - пользователь не подключил бота.
        """
        msg.status = STATUS_UNDELIVERABLE
        msg.attempts += 1
        msg.last_error = error[:2000]
        await self.db.commit()
