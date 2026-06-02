"""OutboundMessage model - журнал и очередь исходящих VK-сообщений."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


# Статусы доставки исходящего сообщения.
STATUS_PENDING = "pending"      # создано, ещё не отправлено
STATUS_SENT = "sent"            # успешно доставлено VK
STATUS_FAILED = "failed"        # транзиентная ошибка, будет повтор
STATUS_UNDELIVERABLE = "undeliverable"  # перманентный отказ (нет разрешения и т.п.)


class OutboundMessage(Base, TimestampMixin):
    """
    Исходящее сообщение боту -> пользователю VK.

    Зачем таблица, а не отправка "на лету":
      1. Аудит. Уведомления о занятиях - бизнес-критичны. Нужно знать, что
         именно ушло, кому и дошло ли. Без журнала рассылка слепая.
      2. Надёжность. VK API может вернуть транзиентную ошибку (сеть, rate
         limit). Запись со status=failed подхватывает retry-воркер и
         повторяет отправку до outbound_max_attempts.
      3. Корректная обработка перманентного отказа. VK не даёт писать
         пользователю, если тот не начал диалог с сообществом и не разрешил
         сообщения (ошибка 901). Это НЕ баг и не повод для ретраев - это
         штатная ситуация "человек не подключил бота". Такое сообщение
         помечается undeliverable и больше не повторяется.

    Источник сообщения (source_event_type / source_event_id) хранится для
    трассировки "какое событие расписания породило это уведомление".
    """

    __tablename__ = "outbound_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Кому. vk_id адресата (а не peer_id - для личных сообщений они совпадают,
    # но семантически это получатель-человек).
    vk_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # user_id платформы, если известен (для аудита; vk_id первичен для отправки).
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Текст сообщения, готовый к отправке.
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Статус доставки (см. константы выше).
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=STATUS_PENDING,
        index=True,
    )

    # Сколько раз пытались отправить.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Последняя ошибка отправки (текст/код VK) - для диагностики.
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Когда успешно отправлено (NULL, пока не отправлено).
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Трассировка источника: тип и id события, породившего сообщение.
    # Для уведомлений из schedule_events - 'lesson.created' и т.п. + event_id.
    source_event_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # Индекс для выборки воркером очереди на повторную отправку:
        # status IN (pending, failed) ORDER BY id.
        Index("ix_outbound_status_id", "status", "id"),
    )

    def __repr__(self) -> str:
        return (
            f"<OutboundMessage(id={self.id}, vk_id={self.vk_id}, "
            f"status={self.status}, attempts={self.attempts})>"
        )
