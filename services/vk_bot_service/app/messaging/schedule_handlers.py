"""
Обработчики событий из exchange 'schedule_events'.

Поток обработки одного события:
  1. Идемпотентность: если event_id уже в processed_events - пропускаем.
  2. В одной транзакции: ставим VK-уведомления в очередь
     (outbound_messages) + пишем event_id в processed_events. Коммит.
  3. После коммита - триггерим отправку поставленных записей. Отправка
     вынесена за транзакцию намеренно: сетевой вызов VK не должен держать
     транзакцию БД, а его сбой не должен откатывать факт обработки события
     (запись уже в очереди со status=pending - её подхватит retry-воркер).

Почему очередь, а не отправка "на лету" внутри транзакции: at-least-once
доставка событий + сетевая отправка несовместимы в одной транзакции без
риска дублей или потерь. Очередь разрывает эту связь надёжно.

event_type берётся из routing_key (consumer), не из payload.
"""
import logging
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.connection import VkBotAsyncSessionLocal
from app.models.outbound_message import OutboundMessage, STATUS_PENDING
from app.repositories.processed_event import ProcessedEventRepository
from app.services.notification_sender import NotificationSender
from app.services.notification_service import VkNotificationService

logger = logging.getLogger(__name__)


# Маппинг event_type -> (метод постановки в очередь у VkNotificationService).
# Заполняется именами методов, вызывается в _process.
_QUEUE_METHODS = {
    "lesson.created": "queue_lesson_created",
    "lesson.cancelled": "queue_lesson_cancelled",
    "lesson.rescheduled": "queue_lesson_rescheduled",
}


async def _flush_outbound(event_id: UUID) -> None:
    """
    Отправить записи очереди, относящиеся к событию (после коммита).

    Берём свежую сессию: пытаемся отправить только что созданные pending-
    записи этого источника. Неотправленные останутся на retry-воркер.
    """
    async with VkBotAsyncSessionLocal() as db:
        result = await db.execute(
            select(OutboundMessage).where(
                OutboundMessage.source_event_id == str(event_id),
                OutboundMessage.status == STATUS_PENDING,
            )
        )
        messages: List[OutboundMessage] = list(result.scalars().all())
        if not messages:
            return
        sender = NotificationSender(db)
        for msg in messages:
            await sender.try_send(msg)


async def _process(event: Dict[str, Any], event_type: str) -> None:
    """Общая обработка события расписания для всех трёх типов."""
    event_id = UUID(str(event["event_id"]))
    queue_method_name = _QUEUE_METHODS[event_type]

    async with VkBotAsyncSessionLocal() as db:
        try:
            processed_repo = ProcessedEventRepository(db)
            if await processed_repo.is_processed(event_id):
                logger.debug("Event already processed, skipping: %s", event_id)
                return

            notif = VkNotificationService(db)
            queue_method = getattr(notif, queue_method_name)
            queued = await queue_method(event)

            await processed_repo.mark_processed(event_id, event_type)
            await db.commit()

            logger.info(
                "%s processed: queued=%d event_id=%s",
                event_type, queued, event_id,
            )
        except IntegrityError as exc:
            # Параллельная обработка того же event_id (гонка реплик/ретраев).
            await db.rollback()
            logger.debug(
                "Event processed concurrently, skipping: %s err=%s",
                event_id, exc,
            )
            return

    # Отправка - после успешного коммита, в отдельной сессии.
    await _flush_outbound(event_id)


async def handle_lesson_created(event: Dict[str, Any]) -> None:
    await _process(event, "lesson.created")


async def handle_lesson_cancelled(event: Dict[str, Any]) -> None:
    await _process(event, "lesson.cancelled")


async def handle_lesson_rescheduled(event: Dict[str, Any]) -> None:
    await _process(event, "lesson.rescheduled")
