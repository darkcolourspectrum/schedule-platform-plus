"""
Клавиатуры VK-бота.

Кнопки несут payload с командой (cmd), по которой диспетчер маршрутизирует
нажатие - это надёжнее, чем разбирать текст кнопки (текст может совпасть
со свободным вводом пользователя). Свободный текст тоже поддерживается
(для шагов ввода имени/email), но навигация по меню - через payload.

Команды (cmd) - единый словарь между keyboards и dispatcher:
  menu           - показать главное меню
  lead           - начать подачу заявки
  schedule       - показать расписание (роль определит, чьё)
  cancel_lesson  - начать отмену занятия (только teacher/admin)
  cancel         - отменить текущий сценарий
  skip           - пропустить необязательный шаг (например телефон)
"""
from typing import Optional

from vkbottle import Keyboard, KeyboardButtonColor, Text

from app.models.user_cache import UserCache


# ==================== КОМАНДЫ ====================

CMD_MENU = "menu"
CMD_LEAD = "lead"
CMD_SCHEDULE = "schedule"
CMD_CANCEL_LESSON = "cancel_lesson"
CMD_CANCEL = "cancel"
CMD_SKIP = "skip"


def _btn(label: str, cmd: str, **extra) -> Text:
    """Кнопка с командой в payload."""
    payload = {"cmd": cmd}
    payload.update(extra)
    return Text(label, payload=payload)


def main_menu(user: Optional[UserCache]) -> str:
    """
    Главное меню. Состав зависит от того, распознан ли пользователь и
    какая у него роль.

    - не распознан (VK не привязан): только подача заявки;
    - student: заявка + моё расписание;
    - teacher/admin: заявка + расписание + отмена занятия.
    """
    kb = Keyboard(one_time=False, inline=False)

    # Заявку может подать кто угодно, даже нераспознанный.
    kb.add(_btn("Оставить заявку", CMD_LEAD), color=KeyboardButtonColor.PRIMARY)

    if user is not None and user.is_active:
        role = user.role_name
        kb.row()
        kb.add(_btn("Моё расписание", CMD_SCHEDULE), color=KeyboardButtonColor.SECONDARY)

        if role in ("teacher", "admin"):
            kb.row()
            kb.add(
                _btn("Отменить занятие", CMD_CANCEL_LESSON),
                color=KeyboardButtonColor.NEGATIVE,
            )

    return kb.get_json()


def cancel_only() -> str:
    """Клавиатура с единственной кнопкой отмены текущего сценария."""
    kb = Keyboard(one_time=False, inline=False)
    kb.add(_btn("Отмена", CMD_CANCEL), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def skip_or_cancel() -> str:
    """Для необязательного шага: пропустить или отменить сценарий."""
    kb = Keyboard(one_time=False, inline=False)
    kb.add(_btn("Пропустить", CMD_SKIP), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(_btn("Отмена", CMD_CANCEL), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def lessons_to_cancel(lessons: list[dict]) -> str:
    """
    Inline-клавиатура со списком занятий на выбор для отмены.

    Каждая кнопка несёт cmd=cancel_lesson + lesson_id. label - дата/время.
    Ограничение VK: не более 10 кнопок в столбце, поэтому вызывающий слой
    передаёт уже усечённый список (например, занятия на сегодня).
    """
    kb = Keyboard(inline=True)
    for i, lesson in enumerate(lessons):
        if i > 0:
            kb.row()
        label = lesson["label"]
        kb.add(
            _btn(label, CMD_CANCEL_LESSON, lesson_id=lesson["lesson_id"]),
            color=KeyboardButtonColor.NEGATIVE,
        )
    return kb.get_json()
