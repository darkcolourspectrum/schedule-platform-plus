"""
Локальный кеш студий в Schedule Service.

Источник данных: события 'studio.created', 'studio.updated', 'studio.deactivated'
из RabbitMQ exchange 'admin_events', публикуемых Admin Service.

Назначение: позволить Schedule Service отдавать списки студий и проверять
их существование без синхронных HTTP-вызовов в Admin Service. При падении
Admin Service Schedule продолжает работать на последних известных данных.

READ-ONLY: запись в эту таблицу делает только consumer (admin_consumer.py
+ admin_handlers.py). Бизнес-логика читает её через StudioCacheRepository.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StudioCache(Base):
    """
    Read-копия студии из Admin Service.
    
    Не имеет своего auto-increment id - первичный ключ совпадает с id
    в Admin Service, чтобы lessons и patterns могли ссылаться на studio_id
    как раньше.
    """
    
    __tablename__ = "studios_cache"
    
    # ID совпадает с Studio.id в Admin Service.
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=False,
    )
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    # occurred_at последнего применённого события. Используется для
    # отбрасывания out-of-order устаревших апдейтов в admin_handlers.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="occurred_at последнего применённого события",
    )
    
    # Когда запись впервые попала в локальный кеш.
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Когда запись впервые попала в локальный кеш",
    )