"""
NotificationSender - единая точка отправки сообщений в VK.

Инкапсулирует связку "VK API + журнал outbound_messages":
  - send_new(): поставить сообщение в очередь и сразу попытаться отправить
    (быстрый путь для свежего события расписания);
  - try_send(msg): попытаться отправить уже существующую запись очереди
    (используется retry-воркером).

Классификация исхода - ключевая ответственность:
  - успех -> mark_sent;
  - VkMessageUndeliverable (901/902: человек не подключил бота) ->
    mark_undeliverable, повторов НЕ будет (штатная ситуация, не ошибка);
  - VkApiError / VkNotConfigured / прочее -> mark_failed, останется в
    очереди до повторной попытки (или до исчерпания лимита).

Создание записи (create) и пометка статуса разнесены, чтобы запись в
журнал происходила в транзакции consumer'а (вместе с processed_events),
а сама отправка - уже после фиксации, не блокируя обработку события.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.vk_api_client import vk_api_client
from app.core.exceptions import (
    VkApiError,
    VkMessageUndeliverable,
    VkNotConfigured,
)
from app.models.outbound_message import OutboundMessage
from app.repositories.outbound_message import OutboundMessageRepository

logger = logging.getLogger(__name__)


class NotificationSender:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OutboundMessageRepository(db)

    async def try_send(self, msg: OutboundMessage) -> bool:
        """
        Попытаться отправить запись очереди и проставить статус.

        Returns:
            True, если доставлено (status=sent); False иначе (failed или
            undeliverable - вызывающему обычно достаточно знать факт).
        """
        try:
            await vk_api_client.send_message(msg.vk_id, msg.message)
        except VkMessageUndeliverable as exc:
            await self.repo.mark_undeliverable(msg, str(exc))
            logger.info(
                "Outbound %s undeliverable to vk_id=%s: %s",
                msg.id, msg.vk_id, exc,
            )
            return False
        except VkNotConfigured as exc:
            # VK не настроен - это не вина сообщения. Оставляем failed, чтобы
            # после настройки VK воркер повторил отправку.
            await self.repo.mark_failed(msg, str(exc))
            logger.warning("Outbound %s deferred (VK not configured)", msg.id)
            return False
        except VkApiError as exc:
            await self.repo.mark_failed(msg, str(exc))
            logger.warning(
                "Outbound %s failed (transient) to vk_id=%s: %s",
                msg.id, msg.vk_id, exc,
            )
            return False
        except Exception as exc:  # неожиданная ошибка - тоже транзиентно
            await self.repo.mark_failed(msg, f"unexpected: {exc}")
            logger.exception("Outbound %s unexpected error", msg.id)
            return False

        await self.repo.mark_sent(msg)
        logger.info("Outbound %s sent to vk_id=%s", msg.id, msg.vk_id)
        return True
