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
from app.messaging.handlers import (
    handle_lesson_created,
    handle_lesson_cancelled,
    handle_lesson_rescheduled,
)

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "schedule_events"
QUEUE_NAME = "notifications.lesson_events"

DLX_NAME = "schedule_events.dlx"
DLQ_NAME = "notifications.lesson_events.dlq"


# Маппинг event_type → handler.
# event_type для маршрутизации берём из routing_key сообщения,
# а не из payload (новая схема outbox).
HANDLERS: Dict[str, Callable[[dict], Awaitable[None]]] = {
    "lesson.created": handle_lesson_created,
    "lesson.cancelled": handle_lesson_cancelled,
    "lesson.rescheduled": handle_lesson_rescheduled,
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
        
        При успехе ack-ает сообщение, при ошибке raise -> reject без re-queue,
        сообщение уйдёт в DLX (схему см. в start()).
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
                raise
            
            # event_type определяем по routing_key, а не из payload
            # (новая схема outbox не содержит event_type в теле).
            event_type = message.routing_key
            handler = HANDLERS.get(event_type)
            
            if handler is None:
                logger.warning(
                    "No handler for routing_key=%s, sending to DLX",
                    message.routing_key,
                )
                raise ValueError(f"No handler for routing_key={message.routing_key}")
            
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


consumer = EventConsumer(amqp_url=settings.rabbitmq_url)