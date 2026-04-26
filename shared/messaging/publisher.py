"""
Универсальный publisher событий в RabbitMQ.

Используется любым сервисом, который хочет опубликовать событие.
Создаётся один раз при старте приложения и переиспользуется.

Топология:
  - exchange типа 'topic' (по умолчанию 'schedule_events')
  - сообщения публикуются с routing_key вида 'lesson.created', 'lesson.cancelled' и т.д.
  - consumers биндят свои очереди к этому exchange по нужным routing keys
"""

import json
import logging
from typing import Any, Dict, Optional

import aio_pika
from aio_pika import ExchangeType, Message, DeliveryMode

logger = logging.getLogger(__name__)


class EventPublisher:
    """Публикатор событий в RabbitMQ через topic exchange."""
    
    def __init__(
        self,
        amqp_url: str,
        exchange_name: str = "schedule_events",
    ):
        self._amqp_url = amqp_url
        self._exchange_name = exchange_name
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None
        self._exchange: Optional[aio_pika.RobustExchange] = None
    
    async def connect(self) -> None:
        """Установить соединение с RabbitMQ. Идемпотентно."""
        if self._connection is not None and not self._connection.is_closed:
            return
        
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self._exchange_name,
            ExchangeType.TOPIC,
            durable=True,
        )
        logger.info(
            "EventPublisher connected: exchange=%s",
            self._exchange_name,
        )
    
    async def close(self) -> None:
        """Закрыть соединение."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("EventPublisher closed")
    
    async def publish(
        self,
        routing_key: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Опубликовать событие.
        
        Args:
            routing_key: например 'lesson.created'
            payload: dict, который будет сериализован в JSON
        """
        if self._exchange is None:
            await self.connect()
        
        body = json.dumps(payload, default=str).encode("utf-8")
        message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        
        await self._exchange.publish(message, routing_key=routing_key)
        logger.info(
            "Event published: routing_key=%s payload_size=%s",
            routing_key, len(body),
        )