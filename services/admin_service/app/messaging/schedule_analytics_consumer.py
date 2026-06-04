"""
RabbitMQ consumer событий Schedule Service для аналитической проекции.

Подписывается на topic exchange 'schedule_events' через очередь
'admin.schedule_events' с биндингом на routing key 'lesson.*'. Наполняет
аналитическую таблицу lesson_facts через handler'ы в
schedule_analytics_handlers.py.

Topology:
    schedule_events (topic, durable)
        └── admin.schedule_events (durable, x-dead-letter-exchange=schedule_events.dlx)
            └── handlers по routing_key (lesson.created/cancelled/rescheduled)

DLX (Dead Letter Exchange):
    schedule_events.dlx УЖЕ объявлен Notification Service как TOPIC durable.
    Объявляем его с теми же параметрами (TOPIC) - RabbitMQ не разрешает
    пере-объявить exchange с другим типом. Своя DLQ: admin.schedule_events.dlq.

Idempotency:
    Обеспечивают сами handler'ы через processed_events.

event_type определяется по routing_key сообщения, а не из payload.
"""

import json
import logging
from typing import Awaitable, Callable, Dict, Optional

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.messaging.schedule_analytics_handlers import (
    handle_lesson_created,
    handle_lesson_cancelled,
    handle_lesson_rescheduled,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "schedule_events"
QUEUE_NAME = "admin.schedule_events"

DLX_NAME = "schedule_events.dlx"
DLQ_NAME = "admin.schedule_events.dlq"


HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "lesson.created": handle_lesson_created,
    "lesson.cancelled": handle_lesson_cancelled,
    "lesson.rescheduled": handle_lesson_rescheduled,
}


class ScheduleEventConsumer:
    """Подписчик на события занятий из Schedule Service."""

    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None

    async def start(self) -> None:
        """Подключиться, объявить топологию, начать слушать очередь."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # DLX уже создан Notification Service как TOPIC durable -
        # объявляем с тем же типом, иначе RabbitMQ вернёт ошибку.
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

        await queue.bind(exchange, routing_key="lesson.*")

        await queue.consume(self._on_message)
        logger.info(
            "ScheduleEventConsumer started: queue=%s bound to %s "
            "with key 'lesson.*', DLQ=%s",
            QUEUE_NAME, EXCHANGE_NAME, DLQ_NAME,
        )

    async def stop(self) -> None:
        """Закрыть соединение."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("ScheduleEventConsumer stopped")

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


consumer = ScheduleEventConsumer(amqp_url=settings.rabbitmq_url)