"""
IncomingMessage - разобранное входящее сообщение и контекст для сценариев.

Собирается диспетчером из апдейта Long Poll и передаётся в обработчик
сценария. Несёт всё, что сценарию нужно: vk_id отправителя, текст,
payload нажатой кнопки (cmd), распознанного пользователя платформы (или
None), а также готовый способ ответить.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.models.user_cache import UserCache


@dataclass
class IncomingMessage:
    vk_id: int
    text: str
    payload: Dict[str, Any] = field(default_factory=dict)
    user: Optional[UserCache] = None

    @property
    def cmd(self) -> Optional[str]:
        """Команда из payload нажатой кнопки (если есть)."""
        return self.payload.get("cmd")

    @property
    def text_lower(self) -> str:
        return (self.text or "").strip().lower()
