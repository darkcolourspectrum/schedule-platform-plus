"""
VK API-клиент: отправка сообщений в личку пользователя через сообщество.

Обёртка над vkbottle.API. Сознательно используем не высокоуровневый
vkbottle.Bot (он перехватывает управление циклом), а низкоуровневый API -
он встраивается в наш собственный воркер/слой отправки в стиле проекта.

Главная ответственность клиента - классификация ошибок VK на:
  - перманентные (нельзя доставить в принципе) -> VkMessageUndeliverable;
  - транзиентные (сеть, rate limit, временный сбой) -> VkApiError (ретрай).
"""
import logging
import random
from typing import Optional

from vkbottle import API
from vkbottle.exception_factory import VKAPIError

from app.config import settings
from app.core.exceptions import (
    VkApiError,
    VkMessageUndeliverable,
    VkNotConfigured,
)

logger = logging.getLogger(__name__)


# Коды ошибок VK, означающие перманентную недоставляемость сообщения.
# Повторять отправку по ним бессмысленно.
#   901 - нельзя писать пользователю: он не разрешил сообщения сообщества
#         (не начал диалог / отписался). Основной случай.
#   902 - нельзя писать из-за настроек приватности пользователя.
_UNDELIVERABLE_CODES = {901, 902}


class VkApiClient:
    """
    Клиент VK для исходящих сообщений сообщества.

    Создаётся один раз при старте приложения. Если VK не настроен
    (нет токена/group_id), клиент поднимается, но любая попытка отправки
    бросает VkNotConfigured - сервис при этом остаётся работоспособным
    (consumer'ы и БД работают, уведомления копятся как undeliverable/pending
    в зависимости от слоя отправки).
    """

    def __init__(self) -> None:
        self._api: Optional[API] = None
        if settings.vk_configured:
            self._api = API(token=settings.vk_group_token)
            logger.info("VkApiClient initialised (group_id=%s)", settings.vk_group_id)
        else:
            logger.warning(
                "VK is not configured (no group token/id) - outgoing messages "
                "will fail with VkNotConfigured until configured."
            )

    @property
    def configured(self) -> bool:
        return self._api is not None

    async def send_message(
        self,
        vk_id: int,
        message: str,
        keyboard: Optional[str] = None,
    ) -> int:
        """
        Отправить личное сообщение пользователю VK.

        Args:
            vk_id: VK id получателя (для лички peer_id == user_id == vk_id).
            message: текст сообщения.
            keyboard: JSON клавиатуры (Keyboard.get_json()) или None.

        Returns:
            message_id отправленного сообщения (int от VK).

        Raises:
            VkNotConfigured: VK-сообщество не настроено.
            VkMessageUndeliverable: перманентный отказ (код 901/902).
            VkApiError: иная ошибка VK (транзиентная, можно повторить).
        """
        if self._api is None:
            raise VkNotConfigured("VK group is not configured")

        # random_id обязателен для messages.send - защита VK от дублей.
        random_id = random.randint(-2_147_483_648, 2_147_483_647)

        send_kwargs = {
            "user_id": vk_id,
            "message": message,
            "random_id": random_id,
        }
        if keyboard is not None:
            send_kwargs["keyboard"] = keyboard

        try:
            result = await self._api.messages.send(**send_kwargs)
        except VKAPIError as exc:
            code = getattr(exc, "code", 0)
            msg = getattr(exc, "error_msg", str(exc))
            if code in _UNDELIVERABLE_CODES:
                logger.info(
                    "Message undeliverable to vk_id=%s (code=%s): %s",
                    vk_id, code, msg,
                )
                raise VkMessageUndeliverable(code, msg) from exc
            logger.warning(
                "VK API error sending to vk_id=%s (code=%s): %s",
                vk_id, code, msg,
            )
            raise VkApiError(code, msg) from exc

        # messages.send для одного user_id возвращает int (message_id).
        if isinstance(result, int):
            return result
        # На случай, если VK вернул список (peer_ids режим) - берём первый id.
        try:
            return int(result[0].message_id)  # type: ignore[index,attr-defined]
        except Exception:  # pragma: no cover - защитный путь
            return 0


# Singleton-экземпляр, создаётся при импорте (как vk_id_client в auth).
vk_api_client = VkApiClient()
