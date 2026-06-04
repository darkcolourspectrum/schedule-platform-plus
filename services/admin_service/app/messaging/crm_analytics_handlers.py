"""
Обработчики событий CRM Service ('crm_events') для аналитической проекции.

Слушаем три события воронки лидов:
    - lead.created          -> создаём ряд в lead_facts (статус new)
    - lead.status_changed   -> обновляем lead_facts + пишем переход
                               в lead_status_transitions (append-only)
    - lead.converted        -> отмечаем конверсию в lead_facts

Каждый handler следует общему паттерну проекта:
    1. Идемпотентность через processed_events (по event_id).
    2. Применение изменений к проекции (upsert / insert).
    3. Запись event_id в processed_events.
    4. Всё в ОДНОЙ транзакции - либо всё, либо ничего.

Out-of-order защита: для lead_facts (mutable-проекция) апдейт применяется
только если occurred_at события новее текущего updated_at записи - тот же
приём, что в users_cache/studios_cache. Для lead_status_transitions защита
не нужна: это append-only лог фактов, каждый переход уникален по
source_event_id, порядок вставки на агрегаты не влияет.

event_type определяется по routing_key в consumer'е, не из payload.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AdminAsyncSessionLocal
from app.models.lead_fact import LeadFact
from app.models.lead_status_transition import LeadStatusTransition
from app.models.processed_event import ProcessedEvent

logger = logging.getLogger(__name__)


# ==================== ОБЩИЕ ХЕЛПЕРЫ ====================


async def _is_already_processed(session: AsyncSession, event_id: UUID) -> bool:
    """Проверить, обрабатывалось ли уже событие с таким event_id."""
    result = await session.execute(
        select(ProcessedEvent.event_id).where(ProcessedEvent.event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_processed(
    session: AsyncSession,
    event_id: UUID,
    event_type: str,
) -> None:
    """Записать event_id в processed_events. Не коммитит."""
    session.add(ProcessedEvent(event_id=event_id, event_type=event_type))


def _parse_dt(raw: Any) -> datetime:
    """
    Распарсить временную метку из payload в aware datetime (UTC).

    Источник присылает occurred_at как ISO 8601 строку. Приводим к
    timezone-aware: naive-значения считаем UTC, чтобы сравнения
    updated_at < occurred_at не падали на разнице aware/naive.
    """
    if isinstance(raw, datetime):
        value = raw
    else:
        value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ==================== HANDLERS ====================


async def handle_lead_created(event: Dict[str, Any]) -> None:
    """
    Обработать 'lead.created' - создать проекцию лида в lead_facts.

    Upsert по id: если ряд уже существует (повторная доставка, или
    lead.status_changed пришёл раньше lead.created), обновляем неизменные
    атрибуты, но только если событие новее (out-of-order защита). Статус
    при создании - тот, что прислан в payload (обычно 'new').
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_dt(event["occurred_at"])
    now = datetime.now(timezone.utc)

    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(LeadFact).values(
                id=event["lead_id"],
                source=event["source"],
                current_status=event["status"],
                studio_id=event.get("studio_id"),
                assigned_to=None,
                lost_reason=None,
                converted_user_id=None,
                is_converted=False,
                lead_created_at=occurred_at,
                converted_at=None,
                updated_at=occurred_at,
                synced_at=now,
            )
            # При конфликте по id - обновляем атрибуты, которые несёт
            # lead.created, но только если событие новее текущего состояния.
            # current_status здесь НЕ трогаем: если уже прилетал
            # status_changed, его статус новее и важнее, чем 'new' из
            # запоздавшего created.
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "source": stmt.excluded.source,
                    "studio_id": stmt.excluded.studio_id,
                    "lead_created_at": stmt.excluded.lead_created_at,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=LeadFact.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "lead.created")
            await session.commit()

            logger.info(
                "lead.created applied: lead_id=%s event_id=%s",
                event["lead_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_lead_status_changed(event: Dict[str, Any]) -> None:
    """
    Обработать 'lead.status_changed'.

    Делает две вещи в одной транзакции:
        1. Обновляет current_status (и lost_reason при уходе в 'lost')
           в lead_facts - с out-of-order защитой по occurred_at.
        2. Пишет неизменяемую запись перехода в lead_status_transitions.

    Если lead_facts ещё нет (status_changed обогнал created), создаём
    минимальный ряд проекции, чтобы не потерять текущий статус. Source/
    studio в нём будут NULL до прихода lead.created, который их дозаполнит.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_dt(event["occurred_at"])
    now = datetime.now(timezone.utc)

    lead_id = event["lead_id"]
    old_status = event.get("old_status")
    new_status = event["new_status"]
    lost_reason = event.get("lost_reason")
    changed_by = event.get("changed_by")

    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            # 1. Текущее состояние в lead_facts.
            #    Upsert: если ряда нет - создаём заготовку с этим статусом.
            #    source NOT NULL в модели, поэтому при вставке-заготовке
            #    подставляем 'unknown' - его перезапишет пришедший позже
            #    lead.created (он новее по логике, но по occurred_at может
            #    быть старше; поэтому source в created обновляется
            #    безусловно-по-времени отдельным апдейтом выше).
            fact_stmt = pg_insert(LeadFact).values(
                id=lead_id,
                source="unknown",
                current_status=new_status,
                studio_id=None,
                assigned_to=changed_by,
                lost_reason=lost_reason,
                converted_user_id=None,
                is_converted=False,
                lead_created_at=occurred_at,
                converted_at=None,
                updated_at=occurred_at,
                synced_at=now,
            )
            fact_stmt = fact_stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "current_status": fact_stmt.excluded.current_status,
                    "lost_reason": fact_stmt.excluded.lost_reason,
                    "updated_at": fact_stmt.excluded.updated_at,
                },
                where=LeadFact.updated_at < fact_stmt.excluded.updated_at,
            )
            await session.execute(fact_stmt)

            # 2. Запись перехода (append-only). Денормализуем source/studio
            #    из текущего состояния факта, чтобы динамику можно было
            #    резать без JOIN. Читаем после апдефта факта.
            fact = await session.get(LeadFact, lead_id)
            source = fact.source if fact else None
            studio_id = fact.studio_id if fact else None

            session.add(
                LeadStatusTransition(
                    lead_id=lead_id,
                    from_status=old_status,
                    to_status=new_status,
                    source=source,
                    studio_id=studio_id,
                    changed_by=changed_by,
                    occurred_at=occurred_at,
                    source_event_id=event_id,
                    synced_at=now,
                )
            )

            await _mark_processed(session, event_id, "lead.status_changed")
            await session.commit()

            logger.info(
                "lead.status_changed applied: lead_id=%s %s->%s event_id=%s",
                lead_id, old_status, new_status, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_lead_converted(event: Dict[str, Any]) -> None:
    """
    Обработать 'lead.converted' - отметить конверсию в lead_facts.

    Проставляет converted_user_id, is_converted=true и converted_at.
    Сам статус ('trial_scheduled' и далее) приходит отдельным событием
    lead.status_changed - конвертация и смена статуса публикуются парой,
    поэтому здесь статус не трогаем, только маркеры конверсии.

    Out-of-order защита по occurred_at. Upsert на случай, если converted
    обогнал created.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_dt(event["occurred_at"])
    now = datetime.now(timezone.utc)

    lead_id = event["lead_id"]
    converted_user_id = event["converted_user_id"]

    async with AdminAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(LeadFact).values(
                id=lead_id,
                source="unknown",
                current_status="trial_scheduled",
                studio_id=None,
                assigned_to=event.get("converted_by"),
                lost_reason=None,
                converted_user_id=converted_user_id,
                is_converted=True,
                lead_created_at=occurred_at,
                converted_at=occurred_at,
                updated_at=occurred_at,
                synced_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "converted_user_id": stmt.excluded.converted_user_id,
                    "is_converted": stmt.excluded.is_converted,
                    "converted_at": stmt.excluded.converted_at,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=LeadFact.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "lead.converted")
            await session.commit()

            logger.info(
                "lead.converted applied: lead_id=%s user_id=%s event_id=%s",
                lead_id, converted_user_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )