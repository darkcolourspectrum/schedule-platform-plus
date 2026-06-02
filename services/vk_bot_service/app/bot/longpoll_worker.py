"""
Long Poll воркер: приём входящих сообщений сообщества.

Использует низкоуровневый BotPolling из vkbottle (не bot.run_forever -
управление циклом остаётся за нами, как у остальных воркеров проекта).
Поллер держит соединение с VK и отдаёт события через async-генератор
listen(); мы разбираем 'message_new', вызываем Dispatcher и отправляем
ответ через VK-клиент.

Запускается фоновой задачей в lifespan. Если VK не настроен - воркер не
стартует (бот при этом остаётся живым: consumer'ы и БД работают, входящих
сообщений просто нет). Это позволяет поднимать сервис без VK-конфигурации.

Каждое сообщение обрабатывается в своей сессии БД и в своей задаче, чтобы
ошибка обработки одного сообщения не роняла весь поллер и не блокировала
приём следующих.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from vkbottle import API, BotPolling

from app.bot.dispatcher import Dispatcher
from app.clients.vk_api_client import vk_api_client
from app.config import settings
from app.core.exceptions import (
    VkApiError,
    VkMessageUndeliverable,
    VkNotConfigured,
)
from app.database.connection import VkBotAsyncSessionLocal

logger = logging.getLogger(__name__)


def _parse_payload(raw: Optional[str]) -> Dict[str, Any]:
    """
    Payload кнопки приходит JSON-строкой (или отсутствует). Разбираем
    безопасно: при отсутствии/битом payload возвращаем пустой dict.
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _extract_message(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Достать объект сообщения из update 'message_new'.

    В актуальном Bots Long Poll API object имеет вид {"message": {...},
    "client_info": {...}}. На случай старого формата (object сразу есть
    message) поддерживаем оба варианта.
    """
    obj = update.get("object") or {}
    if "message" in obj and isinstance(obj["message"], dict):
        return obj["message"]
    # Старый формат: поля сообщения прямо в object.
    if "from_id" in obj or "text" in obj:
        return obj
    return None


class LongPollWorker:
    """Фоновый воркер приёма входящих сообщений VK."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._polling: Optional[BotPolling] = None
        self._stopped = False

    async def start(self) -> None:
        """Запустить поллер фоновой задачей. No-op, если VK не настроен."""
        if not settings.vk_configured:
            logger.warning("VK not configured - Long Poll worker will not start")
            return

        api = API(token=settings.vk_group_token)
        self._polling = BotPolling(
            api=api,
            group_id=settings.vk_group_id,
            wait=settings.vk_longpoll_wait,
        )
        self._task = asyncio.create_task(self._run(), name="vk-longpoll")
        logger.info("Long Poll worker started (group_id=%s)", settings.vk_group_id)

    async def stop(self) -> None:
        """Остановить поллер и дождаться завершения задачи."""
        self._stopped = True
        if self._polling is not None:
            self._polling.stop()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Long Poll worker stopped")

    async def _run(self) -> None:
        """Основной цикл: читаем события и обрабатываем message_new."""
        assert self._polling is not None
        try:
            async for event in self._polling.listen():
                if self._stopped:
                    break
                for update in event.get("updates", []):
                    if update.get("type") != "message_new":
                        continue
                    message = _extract_message(update)
                    if message is None:
                        continue
                    # Обрабатываем в отдельной задаче, чтобы не блокировать
                    # приём следующих событий и изолировать ошибки.
                    asyncio.create_task(self._handle_message(message))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Long Poll loop crashed; worker stopping")

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Обработать одно входящее сообщение и ответить."""
        from_id = message.get("from_id")
        if not from_id or int(from_id) < 0:
            # from_id < 0 - сообщение от сообщества (не от пользователя).
            return

        vk_id = int(from_id)
        text = message.get("text", "") or ""
        payload = _parse_payload(message.get("payload"))

        try:
            async with VkBotAsyncSessionLocal() as db:
                dispatcher = Dispatcher(db)
                reply_text, keyboard = await dispatcher.dispatch(vk_id, text, payload)
        except Exception:
            logger.exception("Dispatch failed for vk_id=%s", vk_id)
            return

        try:
            await vk_api_client.send_message(vk_id, reply_text, keyboard=keyboard)
        except VkMessageUndeliverable as exc:
            # Пользователь сам написал боту, значит обычно доставка возможна;
            # но на всякий случай обрабатываем штатно.
            logger.info("Reply undeliverable to vk_id=%s: %s", vk_id, exc)
        except (VkApiError, VkNotConfigured) as exc:
            logger.warning("Reply send failed to vk_id=%s: %s", vk_id, exc)


worker = LongPollWorker()
