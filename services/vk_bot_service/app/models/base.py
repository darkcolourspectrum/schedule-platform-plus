"""Declarative base and shared mixins for VK Bot Service models."""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


class TimestampMixin:
    """
    Миксин с полями created_at / updated_at.

    Значения проставляются на стороне БД (server_default / onupdate),
    чтобы они были корректны независимо от того, кто пишет запись -
    HTTP-роут, consumer или фоновый воркер.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
