"""
RabbitMQ consumer для событий пользователей (exchange 'auth_events').

Своя durable-очередь 'vk_bot.user_events' с биндингом 'user.*'. Наполняет
users_cache данными пользователей (роль/имя/студия/vk_id), нужными боту
для распознавания собеседников и доставки уведомлений.

Симметричен ScheduleEventConsumer: тот же паттерн DLX/DLQ, та же
маршрутизация по routing_key. role.* боту не нужны - не биндим.
"""
import json
import logging
from typing import Awaitable, Callable, Dict, Optional

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.messaging.auth_handlers import (
    handle_user_created,
    handle_user_deactivated,
    handle_user_updated,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "auth_events"
QUEUE_NAME = "vk_bot.user_events"

DLX_NAME = "auth_events.dlx"
DLQ_NAME = "vk_bot.user_events.dlq"


HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "user.created": handle_user_created,
    "user.updated": handle_user_updated,
    "user.deactivated": handle_user_deactivated,
}


class AuthEventConsumer:
    """Подписчик бота на события пользователей."""

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
        await queue.bind(exchange, routing_key="user.*")

        await queue.consume(self._on_message)
        logger.info(
            "AuthEventConsumer started: queue=%s bound to %s 'user.*'",
            QUEUE_NAME, EXCHANGE_NAME,
        )

    async def stop(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("AuthEventConsumer stopped")

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        event_type = message.routing_key or ""
        handler = HANDLERS.get(event_type)

        if handler is None:
            logger.debug("No handler for routing_key=%s, ack+skip", event_type)
            await message.ack()
            return

        try:
            payload = json.loads(message.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error("Invalid event body, routing to DLQ: %s", exc)
            await message.reject(requeue=False)
            return

        try:
            await handler(payload)
            await message.ack()
        except Exception:
            logger.exception("Handler failed for %s, routing to DLQ", event_type)
            await message.reject(requeue=False)


consumer = AuthEventConsumer(settings.rabbitmq_url)
