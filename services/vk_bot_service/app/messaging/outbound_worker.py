"""
Outbound retry-воркер: повторная доставка VK-сообщений из очереди.

Фоновый цикл (по образцу outbox publisher_worker в других сервисах):
  1. Открывает свою сессию БД.
  2. Берёт батч записей outbound_messages в статусе pending/failed,
     не исчерпавших лимит попыток (fetch_retryable, FOR UPDATE SKIP LOCKED).
  3. Пытается отправить каждую через NotificationSender (он же проставит
     итоговый статус: sent / failed / undeliverable).
  4. Спит poll_interval и повторяет.

Зачем нужен, помимо отправки "на лету" в consumer'е: consumer пытается
отправить сразу после события, но если VK/сеть временно недоступны или
VK ещё не настроен, запись остаётся failed/pending - этот воркер
дотянет её позже. Это и есть гарантия доставки уведомлений.

Записи со статусом undeliverable (901/902 - человек не подключил бота)
воркер не трогает: fetch_retryable их не выбирает. Повтор бессмысленен.
"""
import asyncio
import logging
from typing import Optional

from app.config import settings
from app.database.connection import VkBotAsyncSessionLocal
from app.repositories.outbound_message import OutboundMessageRepository
from app.services.notification_sender import NotificationSender

logger = logging.getLogger(__name__)


class OutboundRetryWorker:
    """Фоновый воркер повторной отправки исходящих сообщений."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="vk-outbound-retry")
        logger.info(
            "Outbound retry worker started (interval=%.1fs, batch=%d, max_attempts=%d)",
            settings.outbound_poll_interval_seconds,
            settings.outbound_batch_size,
            settings.outbound_max_attempts,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Outbound retry worker stopped")

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self._process_batch()
                except Exception:
                    # Сбой одной итерации не должен останавливать воркер.
                    logger.exception("Outbound retry batch failed")
                await asyncio.sleep(settings.outbound_poll_interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _process_batch(self) -> None:
        """Обработать один батч сообщений на (повторную) отправку."""
        async with VkBotAsyncSessionLocal() as db:
            repo = OutboundMessageRepository(db)
            messages = await repo.fetch_retryable(settings.outbound_batch_size)
            if not messages:
                return

            sender = NotificationSender(db)
            sent = 0
            for msg in messages:
                if await sender.try_send(msg):
                    sent += 1
            logger.info(
                "Outbound retry batch: picked=%d sent=%d", len(messages), sent
            )


worker = OutboundRetryWorker()
