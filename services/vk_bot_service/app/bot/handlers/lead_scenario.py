"""
Сценарий подачи заявки (lead).

FSM-шаги (scenario='lead'):
  await_name  -> приняли имя, спрашиваем email
  await_email -> провалидировали email, спрашиваем телефон (опц.)
  await_phone -> приняли/пропустили телефон, создаём лид в CRM

Состояние и накопленные данные хранятся в dialog_states. Создание лида -
через crm_client.create_public_lead (та же публичная ручка, что и лендинг;
сервер проставит source=landing, status=new).

Валидация email - тем же email-validator, что стоит за pydantic EmailStr
в CRM, чтобы не было расхождения "бот принял, CRM отвергла".
"""
import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.context import IncomingMessage
from app.bot.keyboards import cancel_only, main_menu, skip_or_cancel
from app.clients.crm_client import crm_client
from app.core.exceptions import ExternalServiceError
from app.repositories.dialog_state import DialogStateRepository

logger = logging.getLogger(__name__)

SCENARIO = "lead"

STATE_AWAIT_NAME = "await_name"
STATE_AWAIT_EMAIL = "await_email"
STATE_AWAIT_PHONE = "await_phone"


class LeadScenario:
    """
    Обработчик сценария заявки.

    Возвращает кортеж (text, keyboard_json) - что отправить пользователю.
    Диспетчер берёт его и шлёт через VK-клиент. Так сценарий не зависит от
    транспорта и тестируем в изоляции.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dialogs = DialogStateRepository(db)

    async def start(self, msg: IncomingMessage) -> tuple[str, str]:
        """Начать сценарий: спросить имя. Если имя известно из кеша - можно
        было бы предзаполнить, но заявку может подавать и нераспознанный
        человек, поэтому всегда спрашиваем явно."""
        await self.dialogs.set(
            vk_id=msg.vk_id,
            scenario=SCENARIO,
            state=STATE_AWAIT_NAME,
            data={},
        )
        return texts.LEAD_ASK_NAME, cancel_only()

    async def handle(self, msg: IncomingMessage, state: str, data: dict) -> tuple[str, str]:
        """Обработать ввод на текущем шаге сценария."""
        if state == STATE_AWAIT_NAME:
            return await self._on_name(msg, data)
        if state == STATE_AWAIT_EMAIL:
            return await self._on_email(msg, data)
        if state == STATE_AWAIT_PHONE:
            return await self._on_phone(msg, data)
        # Неизвестный шаг - сбрасываем сценарий в меню.
        await self.dialogs.clear(msg.vk_id)
        return texts.MENU_PROMPT, main_menu(msg.user)

    async def _on_name(self, msg: IncomingMessage, data: dict) -> tuple[str, str]:
        name = msg.text.strip()
        if not name:
            return texts.LEAD_ASK_NAME, cancel_only()
        data["name"] = name
        await self.dialogs.set(
            vk_id=msg.vk_id, scenario=SCENARIO, state=STATE_AWAIT_EMAIL, data=data
        )
        return texts.LEAD_ASK_EMAIL, cancel_only()

    async def _on_email(self, msg: IncomingMessage, data: dict) -> tuple[str, str]:
        raw = msg.text.strip()
        try:
            # check_deliverability=False: не ходим в DNS (нет сети к MX из
            # контейнера и не нужно для UX). Формат проверяем строго.
            valid = validate_email(raw, check_deliverability=False)
            email = valid.normalized
        except EmailNotValidError:
            return texts.LEAD_INVALID_EMAIL, cancel_only()
        data["email"] = email
        await self.dialogs.set(
            vk_id=msg.vk_id, scenario=SCENARIO, state=STATE_AWAIT_PHONE, data=data
        )
        return texts.LEAD_ASK_PHONE, skip_or_cancel()

    async def _on_phone(self, msg: IncomingMessage, data: dict) -> tuple[str, str]:
        # Телефон опционален: кнопка "Пропустить" приходит как cmd=skip,
        # это разруливает диспетчер, сюда дойдёт только текстовый ввод.
        phone: Optional[str] = msg.text.strip() or None
        return await self._finish(msg, data, phone)

    async def skip_phone(self, msg: IncomingMessage, data: dict) -> tuple[str, str]:
        """Вызывается диспетчером при нажатии 'Пропустить' на шаге телефона."""
        return await self._finish(msg, data, phone=None)

    async def _finish(
        self, msg: IncomingMessage, data: dict, phone: Optional[str]
    ) -> tuple[str, str]:
        name = data.get("name", "")
        email = data.get("email", "")
        try:
            await crm_client.create_public_lead(
                name=name,
                email=email,
                phone=phone,
            )
        except ExternalServiceError as exc:
            logger.error("Lead creation failed for vk_id=%s: %s", msg.vk_id, exc)
            await self.dialogs.clear(msg.vk_id)
            return texts.LEAD_FAILED, main_menu(msg.user)

        await self.dialogs.clear(msg.vk_id)
        logger.info("Lead submitted via bot: vk_id=%s email=%s", msg.vk_id, email)
        return texts.LEAD_DONE.format(name=name), main_menu(msg.user)
