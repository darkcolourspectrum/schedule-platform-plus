"""
Модель UserCache - локальная read-only копия пользователей из Auth Service.

Зачем нужна:
    CRM назначает лиды на ответственных админов (Lead.assigned_to). Чтобы
    валидировать назначение (нельзя назначить на несуществующего юзера)
    и показывать фронту имя ответственного вместо голого id, CRM нужна
    локальная копия данных пользователей.

    Прямой синхронный запрос в Auth Service на каждый показ списка лидов
    создавал бы лишнюю связанность и нагрузку. Вместо этого CRM держит
    денормализованную копию, которую наполняет consumer событий auth_events.

Принцип "хранить минимум":
    Событие user.created несёт полный снимок пользователя, но CRM кладёт
    в кеш только поля, реально нужные для работы с лидами: id, имя,
    роль, активность. Email, phone, verified-флаги и т.п. сюда не тащим -
    меньше полей означает меньше связанности с моделью Auth Service.

Read-only:
    Эта таблица никогда не пишется бизнес-логикой CRM напрямую - только
    consumer'ом из событий. Источник истины - Auth Service.

Soft-delete:
    user.deactivated НЕ удаляет запись, а ставит is_active=false. Запись
    остаётся, потому что Lead.assigned_to и LeadActivity.created_by могут
    исторически ссылаться на этот id - удаление сломало бы отображение
    старых данных.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserCache(Base):
    """Локальная read-only копия пользователя из Auth Service."""

    __tablename__ = "users_cache"

    # id совпадает с User.id в Auth Service - не автоинкремент, приходит
    # из события.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Имя роли ('admin', 'teacher', ...). Нужно, чтобы CRM мог проверить:
    # лид можно назначить только на пользователя с ролью admin.
    role_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Студия пользователя. Без FK - studios в admin_service_db.
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Активен ли пользователь. user.deactivated ставит false (soft-delete).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # occurred_at последнего применённого события. Используется для
    # out-of-order защиты: событие старше updated_at игнорируется.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Когда запись была синхронизирована (для диагностики лагов).
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:
        return (
            f"<UserCache(id={self.id}, name='{self.full_name}', "
            f"role={self.role_name}, active={self.is_active})>"
        )