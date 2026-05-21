"""
Функции записи событий CRM в outbox-таблицу.

Все функции принимают активную AsyncSession и добавляют EventOutbox-запись
через session.add(). Commit делает вызывающий код (сервисный слой) в той
же транзакции с бизнес-операцией - это и обеспечивает транзакционную
гарантию outbox-паттерна: либо лид и событие сохранятся вместе, либо
ничего.

НЕЛЬЗЯ:
    - вызывать session.commit() внутри этих функций;
    - открывать собственную сессию.

МОЖНО:
    - вызывать в любом месте, где есть активная сессия;
    - вызывать после flush() лида (нужен lead.id).

Routing key совпадает с event_type. События публикуются воркером в
exchange 'crm_events'.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.schemas import (
    LeadConvertedPayload,
    LeadCreatedPayload,
    LeadStatusChangedPayload,
)
from app.models.event_outbox import EventOutbox
from app.models.lead import Lead

logger = logging.getLogger(__name__)


async def record_lead_created(session: AsyncSession, lead: Lead) -> None:
    """
    Записать событие 'lead.created' в outbox.

    Вызывать после flush() лида - в payload нужен lead.id.
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = LeadCreatedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        lead_id=lead.id,
        name=lead.name,
        phone=lead.phone,
        email=lead.email,
        source=lead.source,
        status=lead.status,
        studio_id=lead.studio_id,
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="lead",
            aggregate_id=str(lead.id),
            event_type="lead.created",
            routing_key="lead.created",
            payload=payload.model_dump(mode="json"),
        )
    )
    logger.debug("Recorded lead.created in outbox: lead_id=%s", lead.id)


async def record_lead_status_changed(
    session: AsyncSession,
    lead: Lead,
    old_status: str,
    new_status: str,
    changed_by: int,
) -> None:
    """
    Записать событие 'lead.status_changed' в outbox.

    old_status / new_status передаются явно: к моменту вызова lead.status
    уже содержит новое значение, а старое известно только вызывающему коду.
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = LeadStatusChangedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        lead_id=lead.id,
        old_status=old_status,
        new_status=new_status,
        lost_reason=lead.lost_reason,
        changed_by=changed_by,
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="lead",
            aggregate_id=str(lead.id),
            event_type="lead.status_changed",
            routing_key="lead.status_changed",
            payload=payload.model_dump(mode="json"),
        )
    )
    logger.debug(
        "Recorded lead.status_changed in outbox: lead_id=%s %s->%s",
        lead.id, old_status, new_status,
    )


async def record_lead_converted(
    session: AsyncSession,
    lead: Lead,
    converted_user_id: int,
    converted_by: int,
) -> None:
    """
    Записать событие 'lead.converted' в outbox.

    Публикуется при конвертации лида в клиента. converted_user_id -
    id созданного в Auth Service пользователя.
    """
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)

    payload = LeadConvertedPayload(
        event_id=event_id,
        occurred_at=occurred_at,
        lead_id=lead.id,
        converted_user_id=converted_user_id,
        converted_by=converted_by,
    )

    session.add(
        EventOutbox(
            event_id=event_id,
            aggregate_type="lead",
            aggregate_id=str(lead.id),
            event_type="lead.converted",
            routing_key="lead.converted",
            payload=payload.model_dump(mode="json"),
        )
    )
    logger.debug(
        "Recorded lead.converted in outbox: lead_id=%s user_id=%s",
        lead.id, converted_user_id,
    )


__all__ = [
    "record_lead_created",
    "record_lead_status_changed",
    "record_lead_converted",
]