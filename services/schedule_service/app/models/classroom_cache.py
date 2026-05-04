"""
Локальный кеш кабинетов в Schedule Service.

Источник данных: события 'classroom.created', 'classroom.updated',
'classroom.deactivated' из RabbitMQ exchange 'admin_events'.

READ-ONLY: запись делает только consumer.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClassroomCache(Base):
    """
    Read-копия кабинета из Admin Service.
    """
    
    __tablename__ = "classrooms_cache"
    
    # ID совпадает с Classroom.id в Admin Service.
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=False,
    )
    
    # Привязка к студии - локальная (через id в studios_cache).
    # Без FK constraint, чтобы события могли приходить в любом порядке.
    studio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    equipment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    floor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    room_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="occurred_at последнего применённого события",
    )
    
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Когда запись впервые попала в локальный кеш",
    )
    
    __table_args__ = (
        Index("ix_classrooms_cache_studio_id", "studio_id"),
        Index(
            "ix_classrooms_cache_studio_active",
            "studio_id",
            "is_active",
        ),
    )