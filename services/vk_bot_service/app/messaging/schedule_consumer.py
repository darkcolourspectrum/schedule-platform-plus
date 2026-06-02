"""
RabbitMQ consumer для событий расписания (exchange 'schedule_events').

Независимый от notification_service потребитель: своя durable-очередь
'vk_bot.lesson_events' с биндингом 'lesson.*'. Тот факт, что эти же
события слушает notification_service, не мешает - в topic exchange каждая
очередь получает свою копию сообщения.

DLX/DLQ: битые сообщения (исключение в обработчике) уходят в
'vk_bot.lesson_events.dlq' через dead-letter exchange для ручного разбора.

event_type определяется по routing_key сообщения (delivery), а не из
payload - так задумано в схеме outbox Schedule Service.
"""
import json
import logging
from typing import Awaitable, Callable, Dict, Optional

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.messaging.schedule_handlers import (
    handle_lesson_cancelled,
    handle_lesson_created,
    handle_lesson_rescheduled,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "schedule_events"
QUEUE_NAME = "vk_bot.lesson_events"

DLX_NAME = "schedule_events.dlx"
DLQ_NAME = "vk_bot.lesson_events.dlq"


HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "lesson.created": handle_lesson_created,
    "lesson.cancelled": handle_lesson_cancelled,
    "lesson.rescheduled": handle_lesson_rescheduled,
}


class ScheduleEventConsumer:
    """Подписчик бота на события расписания."""

    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        dlx = await self._channel.declare_exchange(
            DLX_NAME, ExchangeType.TOPIC, durable=True
        )
        dlq = await self._channel.declare_queue(DLQ_NAME, durable=True)
        await dlq.bind(dlx, routing_key="#")

        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )

        queue = await self._channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={"x-dead-letter-exchange": DLX_NAME},
        )
        await queue.bind(exchange, routing_key="lesson.*")

        await queue.consume(self._on_message)
        logger.info(
            "ScheduleEventConsumer started: queue=%s bound to %s 'lesson.*'",
            QUEUE_NAME, EXCHANGE_NAME,
        )

    async def stop(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("ScheduleEventConsumer stopped")

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        # event_type - из routing_key сообщения.
        event_type = message.routing_key or ""
        handler = HANDLERS.get(event_type)

        if handler is None:
            # Не наш тип события - подтверждаем и игнорируем (на всякий
            # случай, если биндинг шире, чем зарегистрированные handlers).
            logger.debug("No handler for routing_key=%s, ack+skip", event_type)
            await message.ack()
            return

        try:
            payload = json.loads(message.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            # Невалидный JSON - в DLQ (reject без requeue).
            logger.error("Invalid event body, routing to DLQ: %s", exc)
            await message.reject(requeue=False)
            return

        try:
            await handler(payload)
            await message.ack()
        except Exception as exc:
            # Ошибка обработки - в DLQ для разбора. Не requeue, чтобы не
            # зациклить битое сообщение (идемпотентность защитит от потери
            # уже сделанной работы при ручном повторе).
            logger.exception("Handler failed for %s, routing to DLQ", event_type)
            await message.reject(requeue=False)


consumer = ScheduleEventConsumer(settings.rabbitmq_url)
