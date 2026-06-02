"""
Dispatcher - маршрутизация входящих сообщений в сценарии.

Логика обработки одного сообщения:
  1. Резолвим отправителя по vk_id (UserResolver -> users_cache).
  2. Глобальные команды имеют приоритет над активным сценарием:
       - cmd=cancel -> прервать любой сценарий, показать меню;
       - cmd=menu / приветственные слова -> показать меню.
  3. Если есть активный сценарий (dialog_states) - отдаём ввод ему,
     КРОМЕ случая глобальной команды выше.
  4. Иначе разбираем команду запуска сценария (cmd=lead/schedule/
     cancel_lesson) или свободный текст.
  5. Любой нераспознанный ввод -> подсказка + меню.

Диспетчер сам ничего не отправляет в VK: каждый обработчик возвращает
(text, keyboard_json), а отправку делает вызывающий слой (Long Poll
воркер) через VK-клиент. Это держит диспетчер свободным от транспорта
и тестируемым.

Доступность ролевых действий проверяется здесь до входа в сценарий:
расписание - для распознанных активных пользователей; отмена занятия -
только teacher/admin. Нераспознанному доступна лишь подача заявки.
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.context import IncomingMessage
from app.bot.handlers.cancel_scenario import (
    CancelLessonScenario,
)
from app.bot.handlers.lead_scenario import (
    LeadScenario,
    SCENARIO as LEAD_SCENARIO,
    STATE_AWAIT_PHONE,
)
from app.bot.handlers.schedule_scenario import ScheduleScenario
from app.repositories.dialog_state import DialogStateRepository
from app.services.user_resolver import UserResolver

logger = logging.getLogger(__name__)


# Свободный текст, который трактуем как "покажи меню" (приветствия, /start).
_MENU_TRIGGERS = {"начать", "старт", "/start", "start", "меню", "привет", "menu"}


class Dispatcher:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.resolver = UserResolver(db)
        self.dialogs = DialogStateRepository(db)
        self.lead = LeadScenario(db)
        self.schedule = ScheduleScenario(db)
        self.cancel = CancelLessonScenario(db)

    async def dispatch(self, vk_id: int, text: str, payload: dict) -> tuple[str, str]:
        """
        Обработать входящее сообщение. Возвращает (text, keyboard_json)
        для отправки пользователю.
        """
        user = await self.resolver.resolve_by_vk_id(vk_id)
        msg = IncomingMessage(vk_id=vk_id, text=text or "", payload=payload or {}, user=user)

        # --- 1. Глобальная отмена: прерывает любой активный сценарий. ---
        if msg.cmd == keyboards.CMD_CANCEL:
            await self.dialogs.clear(vk_id)
            return texts.SCENARIO_CANCELLED, keyboards.main_menu(user)

        # --- 2. Активный сценарий (если есть и это не глобальная команда). ---
        state = await self.dialogs.get(vk_id)
        if state is not None:
            routed = await self._route_active_scenario(msg, state.scenario, state.state, state.data or {})
            if routed is not None:
                return routed
            # Сценарий не распознал состояние - сбрасываем и продолжаем как меню.
            await self.dialogs.clear(vk_id)

        # --- 3. Команды запуска сценариев / меню. ---
        return await self._route_command(msg)

    async def _route_active_scenario(
        self, msg: IncomingMessage, scenario: str, state: str, data: dict
    ) -> Optional[tuple[str, str]]:
        """Передать ввод активному сценарию. None - если сценарий неизвестен."""
        if scenario == LEAD_SCENARIO:
            # На шаге телефона кнопка "Пропустить" обрабатывается отдельно.
            if state == STATE_AWAIT_PHONE and msg.cmd == keyboards.CMD_SKIP:
                return await self.lead.skip_phone(msg, data)
            return await self.lead.handle(msg, state, data)
        return None

    async def _route_command(self, msg: IncomingMessage) -> tuple[str, str]:
        """Маршрутизация команды запуска сценария или свободного текста."""
        cmd = msg.cmd

        # Запуск подачи заявки - доступно всем.
        if cmd == keyboards.CMD_LEAD:
            return await self.lead.start(msg)

        # Расписание - распознанным активным пользователям.
        if cmd == keyboards.CMD_SCHEDULE:
            if msg.user is None or not msg.user.is_active:
                return texts.SCHEDULE_NO_ACCESS, keyboards.main_menu(msg.user)
            return await self.schedule.show(msg)

        # Отмена занятия - teacher/admin. Кнопка из списка несёт lesson_id.
        if cmd == keyboards.CMD_CANCEL_LESSON:
            lesson_id = msg.payload.get("lesson_id")
            if lesson_id is not None:
                return await self.cancel.handle_pick(msg, int(lesson_id))
            return await self.cancel.start(msg)

        # Явный показ меню.
        if cmd == keyboards.CMD_MENU:
            return self._menu(msg.user)

        # Свободный текст: приветствие/меню-триггер -> меню.
        if msg.text_lower in _MENU_TRIGGERS:
            return self._menu(msg.user)

        # Всё прочее - подсказка с меню.
        return texts.UNKNOWN_INPUT, keyboards.main_menu(msg.user)

    def _menu(self, user) -> tuple[str, str]:
        if user is not None and user.is_active:
            greeting = texts.GREETING_KNOWN.format(name=user.first_name or "")
        else:
            greeting = texts.GREETING_UNKNOWN
        return greeting, keyboards.main_menu(user)
