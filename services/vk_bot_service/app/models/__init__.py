"""
Экспорт моделей VK Bot Service.

Импорт всех моделей в одном месте нужен, чтобы Alembic видел их через
Base.metadata при автогенерации миграций, а приложение - через единый
вход app.models.
"""
from app.models.base import Base, TimestampMixin
from app.models.dialog_state import DialogState
from app.models.outbound_message import OutboundMessage
from app.models.processed_event import ProcessedEvent
from app.models.user_cache import UserCache
from app.models.user_token import UserToken

__all__ = [
    "Base",
    "TimestampMixin",
    "DialogState",
    "OutboundMessage",
    "ProcessedEvent",
    "UserCache",
    "UserToken",
]
