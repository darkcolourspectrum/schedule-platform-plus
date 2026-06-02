"""DialogState model - состояние пошагового диалога бота с пользователем."""
from typing import Optional

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DialogState(Base, TimestampMixin):
    """
    Состояние конечного автомата диалога для одного VK-собеседника.

    Большинство действий бота требуют нескольких сообщений (например,
    подача заявки: имя -> email -> телефон). Между сообщениями нужно
    помнить, на каком шаге пользователь и что он уже ввёл. HTTP-сервис
    без состояния тут не годится - состояние храним в БД, привязав к vk_id.

    Запись существует только во время активного сценария. Завершение или
    отмена сценария удаляет запись (диалог возвращается в "нет состояния" -
    бот реагирует на команды/кнопки главного меню).

    state - имя текущего шага (например 'lead_await_name'). Конкретные
    значения определяет слой сценариев (app/bot/handlers). Модель не знает
    семантику шагов - хранит строку и произвольные данные.

    data - накопленные на текущем сценарии значения (JSONB). Например
    {"name": "...", "email": "..."} в процессе сбора заявки.
    """

    __tablename__ = "dialog_states"

    # vk_id собеседника - первичный ключ. Один активный сценарий на человека.
    vk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # Имя сценария, к которому относится state (например 'lead', 'cancel_lesson').
    # Позволяет роутить ввод в нужный обработчик, не разбирая state целиком.
    scenario: Mapped[str] = mapped_column(String(50), nullable=False)

    # Текущий шаг внутри сценария.
    state: Mapped[str] = mapped_column(String(64), nullable=False)

    # Накопленные данные сценария.
    data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DialogState(vk_id={self.vk_id}, scenario={self.scenario}, "
            f"state={self.state})>"
        )
