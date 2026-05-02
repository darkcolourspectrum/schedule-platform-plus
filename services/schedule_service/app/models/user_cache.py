"""
Локальная денормализованная копия данных пользователей из Auth Service.

Заменяет прямой READ-ONLY доступ к auth_service_db (Shared Database antipattern)
на event-driven синхронизацию через consumer событий из exchange 'auth_events'.

Жизненный цикл записи:
    - INSERT при получении user.created
    - UPDATE при получении user.updated, role.changed
    - UPDATE is_active=false при получении user.deactivated
      (запись НЕ удаляется - нужна для отображения исторических связей,
       например 'занятие, проведённое деактивированным преподавателем')

Поле updated_at содержит occurred_at из последнего применённого события,
а не текущее время БД. Это нужно для отбрасывания out-of-order событий:
если приходит событие с occurred_at < текущего updated_at - оно устаревшее
и применять его нельзя (consumer должен игнорировать).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserCache(Base):
    """Денормализованная копия User из Auth Service."""
    
    __tablename__ = "users_cache"
    
    # ID совпадает с user.id в Auth Service - используем тот же первичный ключ.
    # autoincrement отключён, ID приходит из событий.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Роль хранится плоско: id + name. Без отдельной таблицы roles -
    # для денормализованной копии это избыточно, имя роли приходит в payload событий.
    role_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Привязка к студии. Может быть NULL (не привязан) или указывать
    # на studio в Admin Service - FK не ставим, потому что Studio в чужой БД.
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    # Активность пользователя. Деактивированные остаются в таблице
    # для целостности исторических данных (lessons на их id ссылаются).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Время последнего применённого события (occurred_at из payload).
    # Используется для отбрасывания out-of-order устаревших событий.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="occurred_at последнего применённого события"
    )
    
    # Время первой синхронизации этой записи (создание в локальной таблице).
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Когда запись впервые попала в локальный кеш"
    )
    
    __table_args__ = (
        # Индексы для типичных запросов из бизнес-логики Schedule:
        #   - все преподаватели студии (role_name + studio_id + is_active)
        #   - все ученики преподавателя (отдельные запросы по role_name)
        Index(
            "ix_users_cache_role_studio_active",
            "role_name", "studio_id", "is_active",
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<UserCache(id={self.id}, email={self.email}, "
            f"role={self.role_name}, active={self.is_active})>"
        )