"""
RabbitMQ consumer для Notification Service.

Подписывается на topic exchange 'schedule_events' через очередь
'notifications.lesson_events' с биндингом на routing keys 'lesson.*'.
Запускается фоновой задачей при старте FastAPI.
"""

import json
import logging
from typing import Optional, Awaitable, Callable, Dict

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.messaging.handlers import handle_lesson_created

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "schedule_events"
QUEUE_NAME = "notifications.lesson_events"


# Маппинг event_type → handler
HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "lesson.created": handle_lesson_created,
}


class EventConsumer:
    """Подписчик на события RabbitMQ."""
    
    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None
    
    async def start(self) -> None:
        """Подключиться и начать слушать очередь."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        
        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )
        
        queue = await self._channel.declare_queue(
            QUEUE_NAME,
            durable=True,
        )
        
        # Биндим очередь на все события lesson.*
        await queue.bind(exchange, routing_key="lesson.*")
        
        await queue.consume(self._on_message)
        logger.info(
            "EventConsumer started: queue=%s bound to %s with key 'lesson.*'",
            QUEUE_NAME, EXCHANGE_NAME,
        )
    
    async def stop(self) -> None:
        """Закрыть соединение."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("EventConsumer stopped")
    
    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """
        Обработать одно сообщение из очереди.
        
        При успехе ack-ает сообщение, при ошибке делает reject без re-queue
        (чтобы битое сообщение не зацикливалось — пойдёт в DLX в будущем).
        """
        async with message.process(requeue=False):
            try:
                body = message.body.decode("utf-8")
                event = json.loads(body)
                event_type = event.get("event_type")
                
                handler = HANDLERS.get(event_type)
                if handler is None:
                    logger.warning(
                        "No handler for event_type=%s routing_key=%s",
                        event_type, message.routing_key,
                    )
                    return
                
                await handler(event)
                logger.info("Event processed: event_type=%s", event_type)
            
            except json.JSONDecodeError as exc:
                logger.error("Invalid JSON in message: %s", exc)
            except Exception as exc:
                logger.exception(
                    "Handler failed: event_type=%s error=%s",
                    event.get("event_type") if "event" in dir() else "unknown",
                    exc,
                )


consumer = EventConsumer(amqp_url=settings.rabbitmq_url)