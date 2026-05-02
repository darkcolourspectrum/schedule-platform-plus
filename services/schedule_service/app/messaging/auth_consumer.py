"""
RabbitMQ consumer для событий Auth Service в Schedule Service.

Подписывается на topic exchange 'auth_events' через очередь
'schedule.auth_events' с биндингом на routing keys 'user.*' и 'role.*'.
Запускается фоновой задачей при старте FastAPI.

Topology:
    auth_events (topic, durable)
        └── schedule.auth_events (durable, x-dead-letter-exchange=auth_events.dlx)
            └── handlers по event_type

DLX (Dead Letter Exchange):
    Сообщения, которые не удалось обработать (битый JSON, неизвестный
    event_type, исключение в handler'е) - попадают в auth_events.dlx
    и накапливаются в очереди schedule.auth_events.dlq для ручного разбора.
    Без DLX битые сообщения молча терялись бы.

Idempotency:
    Идемпотентность обеспечивают сами handler'ы через processed_events.
    Consumer не делает ack до успешной обработки - в случае краха сообщение
    будет переотправлено брокером.
"""

import json
import logging
from typing import Optional, Awaitable, Callable, Dict

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.messaging.auth_handlers import (
    handle_user_created,
    handle_user_updated,
    handle_user_deactivated,
    handle_role_changed,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "auth_events"
QUEUE_NAME = "schedule.auth_events"

DLX_NAME = "auth_events.dlx"
DLQ_NAME = "schedule.auth_events.dlq"


HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "user.created": handle_user_created,
    "user.updated": handle_user_updated,
    "user.deactivated": handle_user_deactivated,
    "role.changed": handle_role_changed,
}


class AuthEventConsumer:
    """Подписчик на события из Auth Service."""
    
    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None
    
    async def start(self) -> None:
        """Подключиться, объявить топологию, начать слушать очередь."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        
        # DLX и DLQ для битых сообщений
        dlx = await self._channel.declare_exchange(
            DLX_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )
        dlq = await self._channel.declare_queue(
            DLQ_NAME,
            durable=True,
        )
        # DLQ ловит всё, что попадает в DLX
        await dlq.bind(dlx, routing_key="#")
        
        # Основной exchange
        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )
        
        # Основная очередь с DLX-настройкой
        queue = await self._channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_NAME,
            },
        )
        
        # Биндим на user.* и role.*
        await queue.bind(exchange, routing_key="user.*")
        await queue.bind(exchange, routing_key="role.*")
        
        await queue.consume(self._on_message)
        logger.info(
            "AuthEventConsumer started: queue=%s bound to %s "
            "with keys ['user.*', 'role.*'], DLQ=%s",
            QUEUE_NAME, EXCHANGE_NAME, DLQ_NAME,
        )
    
    async def stop(self) -> None:
        """Закрыть соединение."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("AuthEventConsumer stopped")
    
    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """
        Обработать одно сообщение из очереди.
        
        При успехе - ack (process() сделает ack автоматически).
        При ошибке - reject без re-queue, сообщение уйдёт в DLX.
        """
        async with message.process(requeue=False):
            try:
                body = message.body.decode("utf-8")
                event = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.error(
                    "Invalid message body, sending to DLX: routing_key=%s err=%s",
                    message.routing_key, exc,
                )
                # Re-raise чтобы process() сделал nack -> сообщение попадёт в DLX
                raise
            
            event_type = event.get("event_type")
            handler = HANDLERS.get(event_type)
            
            if handler is None:
                logger.warning(
                    "No handler for event_type=%s routing_key=%s, sending to DLX",
                    event_type, message.routing_key,
                )
                raise ValueError(f"No handler for event_type={event_type}")
            
            try:
                await handler(event)
                logger.debug(
                    "Event processed: event_type=%s event_id=%s",
                    event_type, event.get("event_id"),
                )
            except Exception as exc:
                logger.exception(
                    "Handler failed, sending to DLX: event_type=%s "
                    "event_id=%s error=%s",
                    event_type, event.get("event_id"), exc,
                )
                raise


consumer = AuthEventConsumer(amqp_url=settings.rabbitmq_url)