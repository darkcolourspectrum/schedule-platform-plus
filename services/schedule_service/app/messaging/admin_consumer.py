"""
Consumer событий из Admin Service.

Подписывается на exchange 'admin_events' с routing keys 'studio.*' и
'classroom.*'. Каждое сообщение передаётся соответствующему handler'у
в admin_handlers.py. Идемпотентность обеспечивается через таблицу
processed_events: handler сначала проверяет был ли event_id уже
обработан, и только потом применяет изменения.

DLX/DLQ topology:
    main exchange: 'admin_events' (topic, durable)
    main queue:    'schedule.admin_events' (durable, x-dead-letter-exchange='admin_events.dlx')
    dlx exchange:  'admin_events.dlx' (fanout, durable)
    dlq queue:     'schedule.admin_events.dlq' (durable)

Сообщения, которые упали в обработке (raised exception), уходят в DLQ
для ручного разбора, не блокируя основную очередь.
"""

import json
import logging
from typing import Optional

from aio_pika import (
    DeliveryMode,
    ExchangeType,
    Message,
    connect_robust,
)
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractRobustConnection,
)

from app.config import settings
from app.messaging.admin_handlers import HANDLERS

logger = logging.getLogger(__name__)


EXCHANGE_NAME = "admin_events"
QUEUE_NAME = "schedule.admin_events"

DLX_NAME = "admin_events.dlx"
DLQ_NAME = "schedule.admin_events.dlq"


class AdminEventConsumer:
    """Consumer событий Admin Service для Schedule Service."""
    
    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: Optional[AbstractRobustConnection] = None
    
    async def start(self) -> None:
        """Подключиться, объявить topology, начать потребление."""
        self._connection = await connect_robust(self._amqp_url)
        channel = await self._connection.channel()
        
        # Quality of service: не более 50 неподтверждённых сообщений
        # одновременно, чтобы не захлебнуться при всплесках.
        await channel.set_qos(prefetch_count=50)
        
        # Объявляем DLX и DLQ
        dlx = await channel.declare_exchange(
            DLX_NAME,
            ExchangeType.FANOUT,
            durable=True,
        )
        dlq = await channel.declare_queue(DLQ_NAME, durable=True)
        await dlq.bind(dlx)
        
        # Основной exchange (Admin Service publisher)
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )
        
        # Основная очередь с привязкой к DLX
        queue = await channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_NAME,
            },
        )
        
        # Слушаем все studio.* и classroom.*
        await queue.bind(exchange, routing_key="studio.*")
        await queue.bind(exchange, routing_key="classroom.*")
        
        await queue.consume(self._on_message)
        logger.info(
            "AdminEventConsumer started: queue=%s bound to %s "
            "with keys ['studio.*', 'classroom.*'], DLQ=%s",
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
        
        Используется requeue=False: при ошибке сообщение уходит в DLX,
        а не возвращается в очередь повторно (это бы создавало бесконечный
        цикл при детерминированных ошибках).
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


consumer = AdminEventConsumer(amqp_url=settings.rabbitmq_url)