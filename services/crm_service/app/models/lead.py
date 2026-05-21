"""
Модель Lead - потенциальный клиент (лид) в воронке CRM.

Ключевой архитектурный принцип: лид и клиент - РАЗНЫЕ записи в разных БД.
Лид живёт здесь, в crm_service_db. Клиент - это User в auth_service_db.
Конвертация не превращает лид в юзера, а создаёт нового юзера и проставляет
в лиде ссылку converted_user_id.

Понятие "лид" не покидает crm-service: остальные сервисы знают только User.
"""

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LeadSource, LeadStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.lead_activity import LeadActivity

def _values(enum_cls) -> list[str]:
    """Список строковых значений enum - для формирования CHECK-констрейнта."""
    return [member.value for member in enum_cls]


def _in_clause(column: str, enum_cls) -> str:
    """
    Собрать SQL-условие 'column IN (...)' для CHECK-констрейнта.

    Значения берутся из Python-enum, а не пишутся строками вручную -
    так список в БД и enum в коде физически не могут разойтись.
    """
    quoted = ", ".join(f"'{value}'" for value in _values(enum_cls))
    return f"{column} IN ({quoted})"


class Lead(Base, TimestampMixin):
    """Потенциальный клиент школы вокала."""

    __tablename__ = "leads"

    __table_args__ = (
        # CHECK-констрейнты с явными именами: имя нужно, чтобы будущая
        # миграция эволюции воронки могла адресовать констрейнт через
        # DROP CONSTRAINT по имени, а не через автосгенерированное.
        CheckConstraint(
            _in_clause("status", LeadStatus),
            name="ck_leads_status",
        ),
        CheckConstraint(
            _in_clause("source", LeadSource),
            name="ck_leads_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- Контактные данные из заявки ---
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Email - основной обязательный контакт. На него идёт связь с лидом
    # и он же используется при конвертации лида в User (User.email).
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Телефон опционален: если человек не хочет работать по телефону,
    # он его не оставляет. Заявка с лендинга валидна и без него.
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # --- Классификация ---
    # Хранится как String + CHECK-констрейнт (см. __table_args__).
    # Значения валидны строго из app.core.enums.LeadSource.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # Статус воронки. default на уровне приложения - новый лид всегда 'new'.
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=LeadStatus.NEW.value,
    )

    # --- Привязки ---
    # Студия, в которую целится заявка (если на лендинге был выбор филиала).
    # Без FK-констрейнта: studios живут в admin_service_db (другая БД).
    studio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # user_id админа, ответственного за лид. Без FK: users в auth_service_db.
    # Соответствие user_id проверяется через локальный users_cache.
    assigned_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Свободные поля ---
    # Краткая сводка по лиду. Детальная история - в lead_activities.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Причина проигрыша - заполняется при переходе в статус 'lost'.
    lost_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # --- Связь с созданным клиентом ---
    # FK "по смыслу" на auth_service User. Реального ForeignKey нет:
    # кросс-БД FK невозможен (паттерн уже применён в User.studio_id).
    # Проставляется при конвертации лида в provisioned-юзера.
    # Заполненность этого поля = маркер идемпотентности конвертации:
    # повторный вызов convert-to-user не создаёт второго юзера.
    converted_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # --- Relationships ---
    activities: Mapped[List["LeadActivity"]] = relationship(
        "LeadActivity",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="LeadActivity.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<Lead(id={self.id}, name='{self.name}', "
            f"status={self.status}, source={self.source})>"
        )

