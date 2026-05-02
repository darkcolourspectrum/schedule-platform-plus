"""
Локальная денормализованная копия данных пользователей из Auth Service.

Заменяет HTTP-вызовы auth_client.get_user_by_id на чтение из локальной
таблицы. Синхронизация через consumer событий из exchange 'auth_events'.

Преимущества:
    - нет сетевого RTT при отображении профиля
    - Profile Service не падает, если Auth недоступен
    - меньше нагрузка на Auth Service

Жизненный цикл записи такой же, как в Schedule/Admin: create/update через
consumer, soft-delete для деактивации (запись сохраняется для исторических
профилей и комментариев).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserCache(Base):
    """Денормализованная копия User из Auth Service."""
    
    __tablename__ = "users_cache"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    role_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Время последнего применённого события (occurred_at из payload)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="occurred_at последнего применённого события"
    )
    
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Когда запись впервые попала в локальный кеш"
    )
    
    __table_args__ = (
        # Для запросов вида "получить всех преподавателей" в публичных профилях
        Index(
            "ix_users_cache_role_active",
            "role_name", "is_active",
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<UserCache(id={self.id}, email={self.email}, "
            f"role={self.role_name}, active={self.is_active})>"
        )