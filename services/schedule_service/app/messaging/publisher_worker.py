"""
Фоновый воркер, публикующий unpublished события из outbox-таблицы в RabbitMQ.

Запускается как asyncio.Task при старте приложения (через lifespan)
и работает в бесконечном цикле:
    1. Открывает свою сессию к БД
    2. Выбирает batch необработанных событий (published_at IS NULL)
       с FOR UPDATE SKIP LOCKED (на будущее, если запустим несколько реплик)
    3. Для каждого события публикует payload в RabbitMQ через EventPublisher
    4. После успешной публикации проставляет published_at
    5. Если публикация упала (RabbitMQ недоступен и т.п.) - инкрементирует
       published_attempts и записывает last_error, событие останется
       в очереди и будет повторно обработано на следующей итерации

Гарантии:
    - at-least-once: событие может быть опубликовано несколько раз
      (если воркер упал между publish и UPDATE), consumer'ы должны
      быть идемпотентны (проверять event_id перед обработкой)
    - порядок внутри одного агрегата: ORDER BY created_at гарантирует FIFO

Topology:
    - exchange 'schedule_events' (topic, durable) - выделенный для событий Schedule Service
    - routing keys: 'lesson.created' (в будущем lesson.updated, lesson.cancelled)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.messaging import EventPublisher
from app.models.event_outbox import EventOutbox
from app.config import settings

logger = logging.getLogger(__name__)


SCHEDULE_EXCHANGE_NAME = "schedule_events"


class OutboxPublisherWorker:
    """
    Фоновый воркер, читающий outbox и публикующий события в RabbitMQ.
    """
    
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        amqp_url: Optional[str] = None,
        poll_interval: Optional[float] = None,
        batch_size: Optional[int] = None,
        max_attempts: Optional[int] = None,
    ):
        self._session_factory = session_factory
        self._amqp_url = amqp_url or settings.rabbitmq_url
        self._poll_interval = poll_interval or settings.outbox_poll_interval_seconds
        self._batch_size = batch_size or settings.outbox_batch_size
        self._max_attempts = max_attempts or settings.outbox_max_attempts
        
        self._publisher = EventPublisher(
            amqp_url=self._amqp_url,
            exchange_name=SCHEDULE_EXCHANGE_NAME,
        )
        
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def start(self) -> None:
        """Подключиться к RabbitMQ и запустить фоновый цикл."""
        await self._publisher.connect()
        self._task = asyncio.create_task(self._run_loop(), name="schedule-outbox-publisher")
        logger.info(
            "Schedule OutboxPublisherWorker started: exchange=%s poll_interval=%ss batch_size=%s",
            SCHEDULE_EXCHANGE_NAME, self._poll_interval, self._batch_size,
        )
    
    async def stop(self) -> None:
        """Graceful shutdown: остановить цикл, дождаться завершения, закрыть RabbitMQ."""
        if self._task is None:
            return
        
        self._stop_event.set()
        
        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Schedule OutboxPublisherWorker stop timeout, cancelling task")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        await self._publisher.close()
        logger.info("Schedule OutboxPublisherWorker stopped")
    
    async def _run_loop(self) -> None:
        """Главный цикл воркера. Работает до получения stop_event."""
        while not self._stop_event.is_set():
            try:
                processed = await self._process_batch()
                
                # Если обработали полный batch - возможно, есть ещё события,
                # сразу идём на следующую итерацию. Если меньше - ждём.
                if processed < self._batch_size:
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._poll_interval,
                        )
                    except asyncio.TimeoutError:
                        pass
            except Exception as exc:
                logger.exception("Schedule OutboxPublisherWorker iteration failed: %s", exc)
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval,
                    )
                except asyncio.TimeoutError:
                    pass
    
    async def _process_batch(self) -> int:
        """
        Обработать batch unpublished событий.
        
        Returns:
            Количество фактически обработанных строк.
        """
        async with self._session_factory() as session:
            query = (
                select(EventOutbox)
                .where(EventOutbox.published_at.is_(None))
                .where(EventOutbox.published_attempts < self._max_attempts)
                .order_by(EventOutbox.created_at)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            
            result = await session.execute(query)
            events = list(result.scalars().all())
            
            if not events:
                return 0
            
            for event in events:
                await self._publish_one(event)
            
            await session.commit()
            return len(events)
    
    async def _publish_one(self, event: EventOutbox) -> None:
        """
        Опубликовать одно событие и обновить его статус в текущей сессии.
        
        Изменения объекта event попадут в БД при commit'е batch'а.
        """
        try:
            await self._publisher.publish(
                routing_key=event.routing_key,
                payload=event.payload,
            )
            
            event.published_at = datetime.now(timezone.utc)
            event.published_attempts = event.published_attempts + 1
            event.last_error = None
            
            logger.debug(
                "Schedule outbox event published: id=%s event_type=%s aggregate=%s:%s",
                event.id, event.event_type, event.aggregate_type, event.aggregate_id,
            )
        except Exception as exc:
            event.published_attempts = event.published_attempts + 1
            event.last_error = str(exc)[:1000]
            
            logger.error(
                "Schedule outbox publish failed: id=%s event_type=%s attempts=%s error=%s",
                event.id, event.event_type, event.published_attempts, exc,
            )
            
            if event.published_attempts >= self._max_attempts:
                logger.critical(
                    "Schedule outbox event exceeded max_attempts and will be skipped: "
                    "id=%s event_type=%s aggregate=%s:%s",
                    event.id, event.event_type,
                    event.aggregate_type, event.aggregate_id,
                )


# Глобальный экземпляр, инициализируется в lifespan приложения
worker: Optional[OutboxPublisherWorker] = None


def init_worker(session_factory: async_sessionmaker[AsyncSession]) -> OutboxPublisherWorker:
    """Инициализация глобального воркера. Вызывается из lifespan main.py."""
    global worker
    if worker is None:
        worker = OutboxPublisherWorker(session_factory=session_factory)
    return worker