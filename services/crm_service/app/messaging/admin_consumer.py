"""
RabbitMQ consumer для событий Admin Service в CRM Service.

Подписывается на topic exchange 'admin_events' через очередь
'crm.admin_events' с биндингом на routing keys 'studio.*'.
События кабинетов (classroom.*) НЕ слушаем - они нам не нужны.

Topology:
    admin_events (topic, durable)
        └── crm.admin_events (durable, x-dead-letter-exchange=admin_events.dlx)
            └── handlers по event_type (studio.created/updated/deactivated)

DLX (Dead Letter Exchange):
    Сообщения, которые не удалось обработать, попадают в admin_events.dlx
    и накапливаются в очереди crm.admin_events.dlq для ручного разбора.

Idempotency:
    Идемпотентность обеспечивают сами handler'ы через processed_events.

event_type определяется по routing_key сообщения, а не из payload -
это надёжнее и не зависит от того, дублируется ли тип внутри тела.
"""

import json
import logging
from typing import Awaitable, Callable, Dict, Optional

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.messaging.admin_handlers import (
    handle_studio_created,
    handle_studio_updated,
    handle_studio_deactivated,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "admin_events"
QUEUE_NAME = "crm.admin_events"

DLX_NAME = "admin_events.dlx"
DLQ_NAME = "crm.admin_events.dlq"


HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "studio.created": handle_studio_created,
    "studio.updated": handle_studio_updated,
    "studio.deactivated": handle_studio_deactivated,
}


class AdminEventConsumer:
    """Подписчик на события из Admin Service."""

    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None

    async def start(self) -> None:
        """Подключиться, объявить топологию, начать слушать очередь."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # DLX и DLQ для битых сообщений.
        dlx = await self._channel.declare_exchange(
            DLX_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )
        dlq = await self._channel.declare_queue(
            DLQ_NAME,
            durable=True,
        )
        await dlq.bind(dlx, routing_key="#")

        # Основной exchange.
        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )

        # Основная очередь с DLX-настройкой.
        queue = await self._channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_NAME,
            },
        )

        # CRM слушает только события студий, не кабинетов.
        await queue.bind(exchange, routing_key="studio.*")

        await queue.consume(self._on_message)
        logger.info(
            "AdminEventConsumer started: queue=%s bound to %s "
            "with key 'studio.*', DLQ=%s",
            QUEUE_NAME, EXCHANGE_NAME, DLQ_NAME,
        )

    async def stop(self) -> None:
        """Закрыть соединение."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("AdminEventConsumer stopped")

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """
        Обработать одно сообщение из очереди.

        При успехе process() автоматически делает ack. При ошибке raise -
        reject без re-queue, сообщение уходит в DLX.
        """
        async with message.process(requeue=False):
            try:
                body = message.body.decode("utf-8")
                event = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.error(
                    "Invalid message body, sending to DLX: "
                    "routing_key=%s err=%s",
                    message.routing_key, exc,
                )
                raise

            event_type = message.routing_key
            handler = HANDLERS.get(event_type)

            if handler is None:
                logger.warning(
                    "No handler for routing_key=%s, sending to DLX",
                    message.routing_key,
                )
                raise ValueError(
                    f"No handler for routing_key={message.routing_key}"
                )

            try:
                await handler(event)
                logger.debug(
                    "Event processed: routing_key=%s event_id=%s",
                    event_type, event.get("event_id"),
                )
            except Exception as exc:
                logger.exception(
                    "Handler failed, sending to DLX: routing_key=%s "
                    "event_id=%s error=%s",
                    event_type, event.get("event_id"), exc,
                )
                raise


consumer = AdminEventConsumer(amqp_url=settings.rabbitmq_url)