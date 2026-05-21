"""
Обработчики событий из exchange 'admin_events' (Admin Service).

CRM подписан только на события студий ('studio.*'); события кабинетов
('classroom.*') не нужны - для модалки конвертации CRM выбирает только
студию, кабинет не выбирается.

Каждый handler:
    1. Проверяет идемпотентность через processed_events.
    2. Применяет изменение к studios_cache (upsert).
    3. Записывает event_id в processed_events.
    4. Всё в одной транзакции.

Out-of-order защита:
    Если приходит более старое событие (occurred_at < studios_cache.updated_at) -
    оно игнорируется, чтобы не откатить более свежие данные.

Soft-delete:
    studio.deactivated НЕ удаляет запись из studios_cache - ставит
    is_active=false. Запись остаётся, потому что Lead.studio_id может
    исторически на неё ссылаться.

Принцип "хранить минимум":
    Событие admin несёт полный снимок студии. CRM берёт из него только
    поля модели StudioCache (id, name, is_active) - description, address,
    phone, email не нужны.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import CrmAsyncSessionLocal
from app.models.processed_event import ProcessedEvent
from app.models.studio_cache import StudioCache

logger = logging.getLogger(__name__)


# ==================== HELPERS ====================


def _parse_occurred_at(event: Dict[str, Any]) -> datetime:
    """Извлечь occurred_at из payload как timezone-aware datetime."""
    raw = event["occurred_at"]
    if isinstance(raw, datetime):
        parsed = raw
    else:
        parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """Привести datetime к timezone-aware (UTC), если он naive."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _is_already_processed(session: AsyncSession, event_id: UUID) -> bool:
    """Проверить, обрабатывалось ли уже событие с таким event_id."""
    result = await session.execute(
        select(ProcessedEvent.event_id).where(
            ProcessedEvent.event_id == event_id
        )
    )
    return result.scalar_one_or_none() is not None


async def _mark_processed(
    session: AsyncSession,
    event_id: UUID,
    event_type: str,
) -> None:
    """Записать event_id в processed_events. Не коммитит."""
    session.add(ProcessedEvent(event_id=event_id, event_type=event_type))


async def _get_existing(session: AsyncSession, studio_id: int) -> StudioCache | None:
    """Получить текущую запись из studios_cache."""
    result = await session.execute(
        select(StudioCache).where(StudioCache.id == studio_id)
    )
    return result.scalar_one_or_none()


# ==================== HANDLERS ====================


async def handle_studio_created(event: Dict[str, Any]) -> None:
    """
    Обработать 'studio.created' - создать запись в studios_cache.

    Upsert: если запись уже существует (повторная доставка или
    studio.updated пришёл раньше), обновляет её.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)

    async with CrmAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(StudioCache).values(
                id=event["studio_id"],
                name=event["name"],
                is_active=event["is_active"],
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": stmt.excluded.name,
                    "is_active": stmt.excluded.is_active,
                    "updated_at": stmt.excluded.updated_at,
                    "synced_at": stmt.excluded.synced_at,
                },
                where=StudioCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "studio.created")
            await session.commit()

            logger.info(
                "studio.created applied: studio_id=%s event_id=%s",
                event["studio_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_studio_updated(event: Dict[str, Any]) -> None:
    """
    Обработать 'studio.updated' - обновить запись в studios_cache.

    Логика идентична studio.created: оба события несут полный снимок,
    consumer просто перезаписывает локальную копию.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)

    async with CrmAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            stmt = pg_insert(StudioCache).values(
                id=event["studio_id"],
                name=event["name"],
                is_active=event["is_active"],
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": stmt.excluded.name,
                    "is_active": stmt.excluded.is_active,
                    "updated_at": stmt.excluded.updated_at,
                    "synced_at": stmt.excluded.synced_at,
                },
                where=StudioCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "studio.updated")
            await session.commit()

            logger.info(
                "studio.updated applied: studio_id=%s event_id=%s",
                event["studio_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_studio_deactivated(event: Dict[str, Any]) -> None:
    """
    Обработать 'studio.deactivated' - soft-delete студии в кеше.

    Запись НЕ удаляется, только is_active=false. Если записи ещё нет
    (deactivated пришёл раньше created) - пропускаем: создавать запись
    на основе deactivated-события нельзя, в нём нет имени.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)
    studio_id = event["studio_id"]

    async with CrmAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            existing = await _get_existing(session, studio_id)
            if existing is None:
                logger.warning(
                    "studio.deactivated for unknown studio_id=%s, skipping cache "
                    "update (marking processed)", studio_id,
                )
            elif _as_aware(existing.updated_at) < occurred_at:
                existing.is_active = False
                existing.updated_at = occurred_at
                existing.synced_at = datetime.now(timezone.utc)
            else:
                logger.debug(
                    "Stale studio.deactivated ignored: studio_id=%s "
                    "(cache newer than event)", studio_id,
                )

            await _mark_processed(session, event_id, "studio.deactivated")
            await session.commit()

            logger.info(
                "studio.deactivated applied: studio_id=%s event_id=%s",
                studio_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )