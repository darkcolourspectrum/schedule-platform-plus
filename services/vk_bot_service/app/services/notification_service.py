"""
VkNotificationService - превращает события расписания в VK-уведомления.

Зеркалит логику notification_service (тексты по типу события), но вместо
in-app уведомления ставит сообщение в очередь outbound_messages, резолвя
user_id -> vk_id. Для каждого студента события создаётся отдельная запись
очереди (у разных студентов разный vk_id и разный исход доставки).

Резолв vk_id: через UserResolver (users_cache). Если vk_id студента
неизвестен (VK не привязан / не дошло событие auth) - запись в очередь НЕ
создаётся: доставить в VK всё равно нельзя, in-app уведомление при этом
создаёт notification_service независимо. Это не потеря: VK - дополнительный
канал, а не единственный.

Методы создают записи через репозиторий (flush, без commit) - коммит
делает вызывающий обработчик события вместе с processed_events.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.outbound_message import OutboundMessageRepository
from app.services.user_resolver import UserResolver

logger = logging.getLogger(__name__)


def _fmt_time(value: str) -> str:
    """ISO-время '14:30:00' -> '14:30'."""
    return value[:5] if value else ""

_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _fmt_date(value: str) -> str:
    """ISO-дата '2026-09-03' -> '3 сентября'."""
    try:
        _, month, day = (int(part) for part in value.split("-"))
        return f"{day} {_MONTHS_GENITIVE[month - 1]}"
    except (ValueError, IndexError):
        return value


def _upcoming_hint(dates: Optional[List[str]]) -> str:
    """
    Хвост сообщения с ближайшей датой, или пусто, если дат нет.

    Дублирует такую же функцию в notification_service намеренно: сервисы
    независимы, общей библиотеки между ними нет, и заводить её ради двух
    строк форматирования дороже, чем держать копию.
    """
    if not dates:
        return ""
    return f" Ближайшее занятие - {_fmt_date(dates[0])}."

class VkNotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.outbound = OutboundMessageRepository(db)
        self.resolver = UserResolver(db)

    async def _queue_for_students(
        self,
        *,
        student_ids: List[int],
        message: str,
        source_event_type: str,
        source_event_id: str,
    ) -> int:
        """
        Поставить сообщение в очередь каждому студенту, чей vk_id известен.

        Returns:
            число поставленных в очередь записей (для логирования).
        """
        queued = 0
        for user_id in student_ids:
            vk_id = await self.resolver.get_vk_id_for_user(user_id)
            if vk_id is None:
                logger.debug(
                    "Skip VK notify: user_id=%s has no known vk_id (event=%s)",
                    user_id, source_event_type,
                )
                continue
            await self.outbound.create(
                vk_id=vk_id,
                user_id=user_id,
                message=message,
                source_event_type=source_event_type,
                source_event_id=source_event_id,
            )
            queued += 1
        return queued

    async def queue_lesson_created(self, event: Dict[str, Any]) -> int:
        date = event["lesson_date"]
        start = _fmt_time(event["start_time"])
        message = (
            f"Вам назначено новое занятие: {date} в {start}. "
            f"Подробности в приложении."
        )
        return await self._queue_for_students(
            student_ids=event.get("student_ids", []),
            message=message,
            source_event_type="lesson.created",
            source_event_id=str(event["event_id"]),
        )

    async def queue_lesson_cancelled(self, event: Dict[str, Any]) -> int:
        date = event["lesson_date"]
        start = _fmt_time(event["start_time"])
        reason = event.get("cancellation_reason")
        message = f"Занятие {date} в {start} отменено."
        if reason:
            message += f" Причина: {reason}"
        return await self._queue_for_students(
            student_ids=event.get("student_ids", []),
            message=message,
            source_event_type="lesson.cancelled",
            source_event_id=str(event["event_id"]),
        )

    async def queue_lesson_rescheduled(self, event: Dict[str, Any]) -> int:
        old_date = event["old_lesson_date"]
        old_start = _fmt_time(event["old_start_time"])
        new_date = event["new_lesson_date"]
        new_start = _fmt_time(event["new_start_time"])
        message = (
            f"Занятие перенесено: с {old_date} {old_start} "
            f"на {new_date} {new_start}."
        )
        return await self._queue_for_students(
            student_ids=event.get("student_ids", []),
            message=message,
            source_event_type="lesson.rescheduled",
            source_event_id=str(event["event_id"]),
        )

    # ==================== СОБЫТИЯ ШАБЛОНОВ ====================
    #
    # Одно сообщение на всё расписание вместо сообщения на каждое занятие.
    # Технический поток generation.* до бота не доходит - иначе ученик
    # получал бы в VK по сообщению каждый раз, когда фоновый воркер
    # продлевает горизонт генерации.

    async def queue_pattern_assigned(self, event: Dict[str, Any]) -> int:
        schedule_text = event.get("schedule_text") or ""
        message = (
            f"Вам назначены регулярные занятия: {schedule_text}."
            f"{_upcoming_hint(event.get('upcoming_dates'))} "
            f"Подробности в приложении."
        )
        return await self._queue_for_students(
            student_ids=event.get("student_ids", []),
            message=message,
            source_event_type="pattern.assigned",
            source_event_id=str(event["event_id"]),
        )

    async def queue_pattern_changed(self, event: Dict[str, Any]) -> int:
        schedule_text = event.get("schedule_text") or ""
        previous = event.get("previous_schedule_text")

        message = f"Расписание регулярных занятий изменилось. Теперь: {schedule_text}."
        if previous:
            message += f" Раньше было: {previous}."
        message += _upcoming_hint(event.get("upcoming_dates"))

        return await self._queue_for_students(
            student_ids=event.get("student_ids", []),
            message=message,
            source_event_type="pattern.changed",
            source_event_id=str(event["event_id"]),
        )

    async def queue_pattern_unassigned(self, event: Dict[str, Any]) -> int:
        previous = event.get("previous_schedule_text") or ""
        message = (
            f"Регулярные занятия по расписанию {previous} отменены. "
            f"Будущие занятия убраны из вашего расписания."
        )
        return await self._queue_for_students(
            student_ids=event.get("student_ids", []),
            message=message,
            source_event_type="pattern.unassigned",
            source_event_id=str(event["event_id"]),
        )