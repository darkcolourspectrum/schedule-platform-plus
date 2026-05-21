"""
Модель StudioCache - локальная read-only копия студий из Admin Service.

Зачем нужна:
    При конвертации лида в клиента CRM должен предложить админу выбрать
    студию из списка. Прямой синхронный запрос в Admin Service создавал
    бы межсервисную зависимость и мешал автономности.

    Вместо этого CRM подписывается на события Admin Service и держит
    собственную денормализованную копию справочника студий. Это тот же
    паттерн, что для users_cache - принцип "хранить минимум": только
    поля, реально используемые CRM-логикой.

Read-only:
    Эта таблица никогда не пишется бизнес-логикой CRM напрямую - только
    consumer'ом из событий. Источник истины - Admin Service.

Soft-delete:
    studio.deleted НЕ удаляет запись, а ставит is_active=false. Студия
    может быть исторически связана с лидами/юзерами, физическое удаление
    сломало бы целостность.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StudioCache(Base):
    """Локальная read-only копия студии из Admin Service."""

    __tablename__ = "studios_cache"

    # id совпадает со Studio.id в Admin Service - не автоинкремент,
    # приходит из события.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Активна ли студия. studio.deleted ставит false (soft-delete).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
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

    def __repr__(self) -> str:
        return (
            f"<StudioCache(id={self.id}, name='{self.name}', "
            f"active={self.is_active})>"
        )