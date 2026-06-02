"""UserCache model - локальная read-копия пользователей платформы."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserCache(Base):
    """
    Read-копия пользователя платформы, нужная боту.

    Назначение - две задачи бота:
      1. Доставка уведомлений: событие расписания несёт student_ids
         (внутренние user_id). Чтобы отправить сообщение в VK, нужен vk_id.
         Эта таблица хранит соответствие user_id <-> vk_id.
      2. Ролевая логика: когда пользователь пишет боту, мы по его vk_id
         находим запись, определяем роль (teacher/student) и user_id для
         вызовов schedule/crm от его имени.

    Наполнение:
      - role/имя/студия/активность - из событий auth_events (user.*),
        полный снимок, как users_cache в других сервисах;
      - vk_id - заполняется когда становится известен: либо из события
        (если человек привязал VK и auth прислал обновление), либо лениво
        при первом входящем сообщении в Long Poll (from_id = доверенный
        vk_id), либо точечным дозапросом к auth по internal API.

    id здесь - это user_id платформы (первичный ключ совпадает с auth.User.id).
    """

    __tablename__ = "users_cache"

    # user_id платформы. Совпадает с auth.User.id.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # VK id пользователя. NULL, пока не стал известен. UNIQUE: один VK = один
    # пользователь (зеркалит инвариант auth, где vk_id UNIQUE). Индексирован
    # для обратного резолва vk_id -> user_id при входящем сообщении.
    vk_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        unique=True,
        index=True,
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    # Имя роли (admin/teacher/student) - денормализовано из события auth.
    role_name: Mapped[str] = mapped_column(String(50), nullable=False, default="student")

    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # occurred_at последнего применённого события auth. Используется для
    # out-of-order защиты: более старое событие не должно перезаписывать
    # более свежее состояние.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Когда запись последний раз синхронизирована (для аудита/диагностики).
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:
        return f"<UserCache(id={self.id}, vk_id={self.vk_id}, role={self.role_name})>"
