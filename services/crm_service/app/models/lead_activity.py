"""
Модель LeadActivity - запись в журнале истории работы с лидом.

Один Lead имеет много LeadActivity. Записи создаются:
    - вручную: админ добавляет заметку (type=note) или отметку о звонке
      (type=call) через эндпоинт POST /leads/{id}/activities;
    - автоматически: при смене статуса лида сервисный слой дописывает
      запись type=status_changed с описанием перехода.

Журнал неизменяемый: записи только добавляются, не редактируются и не
удаляются (кроме каскадного удаления вместе с лидом). Поэтому модель
наследует только created_at - updated_at здесь не имеет смысла, и
TimestampMixin не используется.
"""

from datetime import datetime
from typing import Optional
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LeadActivityType
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.lead import Lead

class LeadActivity(Base):
    """Запись в ленте истории лида."""

    __tablename__ = "lead_activities"

    __table_args__ = (
        CheckConstraint(
            "type IN ("
            + ", ".join(f"'{m.value}'" for m in LeadActivityType)
            + ")",
            name="ck_lead_activities_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Лид, к которому относится запись. FK внутри той же БД (crm_service_db),
    # поэтому констрейнт настоящий. ondelete=CASCADE: удаление лида забирает
    # с собой весь его журнал (дублирует ORM-каскад на случай прямого
    # DELETE в обход сессии).
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Тип записи. String + CHECK-констрейнт, значения из LeadActivityType.
    type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Текст заметки или человекочитаемое описание системного события
    # (например, "Статус: contacted -> trial_scheduled").
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # user_id админа - автора записи. Без FK: users в auth_service_db.
    # NULL допустим для чисто системных записей без инициатора-человека.
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Момент создания записи. Журнал неизменяемый - updated_at не нужен.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    lead: Mapped["Lead"] = relationship("Lead", back_populates="activities")

    def __repr__(self) -> str:
        return (
            f"<LeadActivity(id={self.id}, lead_id={self.lead_id}, "
            f"type={self.type})>"
        )