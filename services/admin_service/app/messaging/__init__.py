"""Messaging модуль Admin Service: outbox-паттерн, публикация и потребление событий."""

from app.messaging.outbox import (
    record_studio_created,
    record_studio_updated,
    record_studio_deactivated,
    record_classroom_created,
    record_classroom_updated,
    record_classroom_deactivated,
)

__all__ = [
    "record_studio_created",
    "record_studio_updated",
    "record_studio_deactivated",
    "record_classroom_created",
    "record_classroom_updated",
    "record_classroom_deactivated",
]