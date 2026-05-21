"""
Pydantic-схемы payload событий, публикуемых CRM Service в RabbitMQ.

Каждое событие несёт ПОЛНЫЙ снимок релевантного состояния лида, а не
diff. Это паттерн всего проекта: consumer просто перезаписывает свою
локальную копию, опираясь на occurred_at для отбрасывания устаревших
(out-of-order) сообщений. Diff потребовал бы от consumer'а знать
предыдущее состояние - лишняя сложность.

Служебные поля есть в каждом payload:
    event_id    - глобальный UUID, consumer использует для идемпотентности;
    occurred_at - момент бизнес-операции, для out-of-order защиты.

Кто слушает эти события сейчас: внутри системы - никто. Лиды намеренно
не видны другим сервисам. Outbox и эти схемы - подготовленная точка
интеграции: lead.converted понадобится на шаге конвертации, а
lead.created/lead.status_changed дают аудит-след и задел под будущую
аналитику конверсии. Exchange позволяет добавлять consumer'ов позже
без изменения publisher'а.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _EventBase(BaseModel):
    """Общие служебные поля любого события CRM."""

    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    occurred_at: datetime


class LeadCreatedPayload(_EventBase):
    """Payload события lead.created - создан новый лид."""

    lead_id: int
    name: str
    phone: Optional[str] = None
    email: str
    source: str
    status: str
    studio_id: Optional[int] = None


class LeadStatusChangedPayload(_EventBase):
    """Payload события lead.status_changed - лид сменил статус воронки."""

    lead_id: int
    old_status: str
    new_status: str
    # Заполняется только при переходе в статус 'lost'.
    lost_reason: Optional[str] = None
    # user_id админа, инициировавшего смену статуса.
    changed_by: int


class LeadConvertedPayload(_EventBase):
    """
    Payload события lead.converted - лид сконвертирован в клиента.

    Схема заведена заранее; record-функция для неё появится на шаге
    конвертации лида в пользователя, чтобы не было мёртвого кода.
    """

    lead_id: int
    # id созданного в Auth Service пользователя.
    converted_user_id: int
    # user_id админа, выполнившего конвертацию.
    converted_by: int