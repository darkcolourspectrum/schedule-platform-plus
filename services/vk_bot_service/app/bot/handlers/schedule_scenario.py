"""
Сценарий просмотра расписания.

Одношаговый (без FSM-состояния): по команде показывает расписание на
ближайшую неделю. Роль определяет, чьё расписание:
  - teacher/admin -> своё преподавательское (teachers/{id});
  - student        -> свои занятия (students/{id}).

Действие идёт в Schedule Service ОТ ИМЕНИ пользователя (JWT), поэтому
сначала добываем access-токен через TokenService. Если токен получить
нельзя (нет аккаунта с таким vk_id) - сообщаем, что нужен аккаунт с
привязанным VK.

Статусы занятий переводим на русский для вывода. Отменённые показываем
с пометкой, не скрываем - пользователю полезно видеть, что занятие было
и отменено.
"""
import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.context import IncomingMessage
from app.bot.keyboards import main_menu
from app.clients.schedule_client import schedule_client
from app.core.exceptions import ExternalServiceError
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)

# Горизонт показа расписания.
_SCHEDULE_DAYS = 7

_STATUS_RU = {
    "scheduled": "",
    "completed": " (проведено)",
    "cancelled": " (отменено)",
    "missed": " (пропущено)",
}


def _fmt_time(value: str) -> str:
    """ISO-время '14:30:00' -> '14:30'."""
    return value[:5] if value else ""


_MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _fmt_date_human(d: date) -> str:
    """date -> '2 июня' (без года, для компактного заголовка периода)."""
    return f"{d.day} {_MONTHS_RU[d.month - 1]}"


def _format_schedule(lessons: list[dict], from_date: date, to_date: date) -> str:
    """Собрать текст расписания из списка ScheduleLessonItem (dict)."""
    period = f"{_fmt_date_human(from_date)} — {_fmt_date_human(to_date)}"
    if not lessons:
        return f"Расписание на период {period}:\nЗанятий нет."

    # Сортируем по дате и времени начала для читаемости.
    def _key(item: dict):
        return (item.get("lesson_date", ""), item.get("start_time", ""))

    lines = [f"Ваше расписание на период {period}:"]
    for item in sorted(lessons, key=_key):
        status_suffix = _STATUS_RU.get(item.get("status", ""), "")
        lines.append(
            texts.SCHEDULE_LINE.format(
                date=item.get("lesson_date", ""),
                start=_fmt_time(item.get("start_time", "")),
                end=_fmt_time(item.get("end_time", "")),
                status=status_suffix,
            )
        )
    return "\n".join(lines)


class ScheduleScenario:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tokens = TokenService(db)

    async def show(self, msg: IncomingMessage) -> tuple[str, str]:
        """
        Показать расписание пользователя. Возвращает (text, keyboard_json).

        msg.user гарантированно не None и активен (диспетчер не вызывает
        этот сценарий для нераспознанных) - но мягко проверим ещё раз.
        """
        user = msg.user
        if user is None or not user.is_active:
            return texts.SCHEDULE_NO_ACCESS, main_menu(user)

        access_token = await self.tokens.get_access_token(user.id, msg.vk_id)
        if access_token is None:
            # vk_id не привязан к аккаунту на платформе - расписания нет.
            return texts.SCHEDULE_NO_ACCESS, main_menu(user)

        from_date = date.today()
        to_date = from_date + timedelta(days=_SCHEDULE_DAYS)

        try:
            if user.role_name in ("teacher", "admin"):
                resp = await schedule_client.get_teacher_schedule(
                    access_token=access_token,
                    teacher_id=user.id,
                    from_date=from_date,
                    to_date=to_date,
                )
            else:
                resp = await schedule_client.get_student_schedule(
                    access_token=access_token,
                    student_id=user.id,
                    from_date=from_date,
                    to_date=to_date,
                )
        except ExternalServiceError as exc:
            logger.error("Schedule fetch failed for user_id=%s: %s", user.id, exc)
            return texts.SCHEDULE_NO_ACCESS, main_menu(user)

        lessons = resp.get("lessons", [])
        return _format_schedule(lessons, from_date, to_date), main_menu(user)