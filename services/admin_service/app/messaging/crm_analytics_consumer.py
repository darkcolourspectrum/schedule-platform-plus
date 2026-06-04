"""
RabbitMQ consumer событий CRM Service для аналитической проекции.

Подписывается на topic exchange 'crm_events' через очередь
'admin.crm_events' с биндингом на routing key 'lead.*'. Наполняет
аналитические таблицы lead_facts и lead_status_transitions через
handler'ы в crm_analytics_handlers.py.

Topology:
    crm_events (topic, durable)
        └── admin.crm_events (durable, x-dead-letter-exchange=crm_events.dlx)
            └── handlers по routing_key (lead.created/status_changed/converted)

DLX (Dead Letter Exchange):
    crm_events.dlx (topic, durable) - битые/необрабатываемые сообщения
    накапливаются в admin.crm_events.dlq для ручного разбора. Admin -
    первый потребитель crm_events в системе, поэтому DLX объявляем здесь.

Idempotency:
    Обеспечивают сами handler'ы через processed_events. Consumer не делает
    ack до успешной обработки - при крахе брокер переотправит сообщение.

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
from app.messaging.crm_analytics_handlers import (
    handle_lead_created,
    handle_lead_status_changed,
    handle_lead_converted,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "crm_events"
QUEUE_NAME = "admin.crm_events"

DLX_NAME = "crm_events.dlx"
DLQ_NAME = "admin.crm_events.dlq"


HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "lead.created": handle_lead_created,
    "lead.status_changed": handle_lead_status_changed,
    "lead.converted": handle_lead_converted,
}


class CrmEventConsumer:
    """Подписчик на события воронки лидов из CRM Service."""

    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None

    async def start(self) -> None:
        """Подключиться, объявить топологию, начать слушать очередь."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # DLX и DLQ для битых сообщений. Admin - первый консьюмер
        # crm_events, объявляем DLX здесь (TOPIC, durable).
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

        await queue.bind(exchange, routing_key="lead.*")

        await queue.consume(self._on_message)
        logger.info(
            "CrmEventConsumer started: queue=%s bound to %s "
            "with key 'lead.*', DLQ=%s",
            QUEUE_NAME, EXCHANGE_NAME, DLQ_NAME,
        )

    async def stop(self) -> None:
        """Закрыть соединение."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("CrmEventConsumer stopped")

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


consumer = CrmEventConsumer(amqp_url=settings.rabbitmq_url)