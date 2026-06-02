"""
Сценарий отмены занятия преподавателем (cancel_lesson).

Шаги:
  1. start(): получить расписание преподавателя на ближайшую неделю,
     отфильтровать отменяемые (status=scheduled, дата >= сегодня),
     показать inline-кнопками (не более 10 - ограничение VK).
  2. handle_pick(): по нажатию кнопки с lesson_id отменить занятие через
     Schedule Service. Это публикует lesson.cancelled -> ученики получат
     уведомление (в т.ч. через нашего же бота - consumer идемпотентен).

Состояние между шагами почти не нужно (lesson_id приходит в payload
кнопки), поэтому FSM-запись не храним: список занятий показывается
inline-клавиатурой, выбор - отдельное нажатие с готовым lesson_id.

Доступ: только teacher/admin. Диспетчер проверяет роль до вызова, но
сценарий тоже мягко проверяет (defense in depth).
"""
import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.context import IncomingMessage
from app.bot.keyboards import lessons_to_cancel, main_menu
from app.clients.schedule_client import schedule_client
from app.core.exceptions import ExternalServiceError
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)

_HORIZON_DAYS = 7
_MAX_BUTTONS = 10


def _fmt_time(value: str) -> str:
    return value[:5] if value else ""


class CancelLessonScenario:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tokens = TokenService(db)

    def _is_allowed(self, msg: IncomingMessage) -> bool:
        return (
            msg.user is not None
            and msg.user.is_active
            and msg.user.role_name in ("teacher", "admin")
        )

    async def start(self, msg: IncomingMessage) -> tuple[str, str]:
        """Показать список предстоящих занятий для отмены."""
        if not self._is_allowed(msg):
            return texts.CANCEL_NOT_ALLOWED, main_menu(msg.user)

        access_token = await self.tokens.get_access_token(msg.user.id, msg.vk_id)
        if access_token is None:
            return texts.CANCEL_NOT_ALLOWED, main_menu(msg.user)

        from_date = date.today()
        to_date = from_date + timedelta(days=_HORIZON_DAYS)
        try:
            resp = await schedule_client.get_teacher_schedule(
                access_token=access_token,
                teacher_id=msg.user.id,
                from_date=from_date,
                to_date=to_date,
            )
        except ExternalServiceError as exc:
            logger.error("Schedule fetch failed (cancel) user_id=%s: %s", msg.user.id, exc)
            return texts.CANCEL_FAILED, main_menu(msg.user)

        # Отменяемы только запланированные занятия.
        scheduled = [
            l for l in resp.get("lessons", [])
            if l.get("status") == "scheduled"
        ]
        if not scheduled:
            return texts.CANCEL_NO_LESSONS, main_menu(msg.user)

        # Сортируем по дате/времени, берём первые N для кнопок.
        scheduled.sort(key=lambda l: (l.get("lesson_date", ""), l.get("start_time", "")))
        buttons = []
        for l in scheduled[:_MAX_BUTTONS]:
            label = f"{l.get('lesson_date','')} {_fmt_time(l.get('start_time',''))}"
            buttons.append({"label": label, "lesson_id": l["lesson_id"]})

        return texts.CANCEL_PICK, lessons_to_cancel(buttons)

    async def handle_pick(self, msg: IncomingMessage, lesson_id: int) -> tuple[str, str]:
        """Отменить выбранное занятие."""
        if not self._is_allowed(msg):
            return texts.CANCEL_NOT_ALLOWED, main_menu(msg.user)

        access_token = await self.tokens.get_access_token(msg.user.id, msg.vk_id)
        if access_token is None:
            return texts.CANCEL_NOT_ALLOWED, main_menu(msg.user)

        try:
            await schedule_client.cancel_lesson(
                access_token=access_token,
                lesson_id=lesson_id,
                reason="Отменено преподавателем через бота",
            )
        except ExternalServiceError as exc:
            logger.error(
                "Cancel lesson failed user_id=%s lesson_id=%s: %s",
                msg.user.id, lesson_id, exc,
            )
            return texts.CANCEL_FAILED, main_menu(msg.user)

        logger.info(
            "Lesson cancelled via bot: user_id=%s lesson_id=%s",
            msg.user.id, lesson_id,
        )
        return texts.CANCEL_DONE, main_menu(msg.user)
