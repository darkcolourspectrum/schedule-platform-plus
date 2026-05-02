"""Messaging модуль Auth Service: outbox-паттерн и публикация событий."""

from app.messaging.outbox import (
    record_user_created,
    record_user_updated,
    record_user_deactivated,
    record_role_changed,
)

__all__ = [
    "record_user_created",
    "record_user_updated",
    "record_user_deactivated",
    "record_role_changed",
]