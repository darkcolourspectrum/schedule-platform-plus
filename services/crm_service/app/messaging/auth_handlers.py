"""
Обработчики событий из exchange 'auth_events' (Auth Service).

Каждый handler:
    1. Проверяет идемпотентность через таблицу processed_events.
       Если event_id уже обработан - пропускает.
    2. Применяет изменение к users_cache (upsert).
    3. Записывает event_id в processed_events.
    4. Всё в одной транзакции - либо всё, либо ничего.

Out-of-order защита:
    Если приходит более старое событие (occurred_at < users_cache.updated_at) -
    оно игнорируется, чтобы не откатить более свежие данные. Сценарий
    редкий, но возможен при ретраях publisher'а.

Soft-delete для деактивации:
    user.deactivated НЕ удаляет запись из users_cache - ставит is_active=false.
    Запись остаётся, потому что Lead.assigned_to и LeadActivity.created_by
    могут исторически ссылаться на этот id.

Принцип "хранить минимум":
    Событие auth несёт полный снимок пользователя. CRM берёт из него только
    поля модели UserCache (id, имена, роль, студия, активность) - остальное
    (email, phone, verified-флаги) для работы с лидами не нужно.
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
from app.models.user_cache import UserCache

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
    """
    Привести datetime к timezone-aware (UTC), если он naive.

    Колонки TIMESTAMP WITH TIME ZONE в PostgreSQL всегда отдают aware
    datetime, но эта защита делает сравнение occurred_at с updated_at
    устойчивым к любому источнику naive-значения (ручная вставка,
    миграция данных). Без неё сравнение naive и aware datetime упало бы
    с TypeError.
    """
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


async def _get_existing(session: AsyncSession, user_id: int) -> UserCache | None:
    """Получить текущую запись из users_cache."""
    result = await session.execute(
        select(UserCache).where(UserCache.id == user_id)
    )
    return result.scalar_one_or_none()


# ==================== HANDLERS ====================


async def handle_user_created(event: Dict[str, Any]) -> None:
    """
    Обработать 'user.created' - создать запись в users_cache.

    Upsert: если запись уже существует, обновляет её (защита от повторной
    доставки и от ситуации, когда user.updated пришёл раньше user.created).
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

            stmt = pg_insert(UserCache).values(
                id=event["user_id"],
                first_name=event["first_name"],
                last_name=event["last_name"],
                role_name=event["role_name"],
                studio_id=event.get("studio_id"),
                is_active=event["is_active"],
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )
            # При конфликте по id - обновляем, но только если событие
            # новее текущего состояния (out-of-order защита).
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "first_name": stmt.excluded.first_name,
                    "last_name": stmt.excluded.last_name,
                    "role_name": stmt.excluded.role_name,
                    "studio_id": stmt.excluded.studio_id,
                    "is_active": stmt.excluded.is_active,
                    "updated_at": stmt.excluded.updated_at,
                    "synced_at": stmt.excluded.synced_at,
                },
                where=UserCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "user.created")
            await session.commit()

            logger.info(
                "user.created applied: user_id=%s event_id=%s",
                event["user_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_user_updated(event: Dict[str, Any]) -> None:
    """
    Обработать 'user.updated' - обновить запись в users_cache.

    Логика идентична user.created: оба события несут полный снимок,
    consumer просто перезаписывает локальную копию. Upsert на случай,
    если user.updated пришёл раньше user.created.
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

            stmt = pg_insert(UserCache).values(
                id=event["user_id"],
                first_name=event["first_name"],
                last_name=event["last_name"],
                role_name=event["role_name"],
                studio_id=event.get("studio_id"),
                is_active=event["is_active"],
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "first_name": stmt.excluded.first_name,
                    "last_name": stmt.excluded.last_name,
                    "role_name": stmt.excluded.role_name,
                    "studio_id": stmt.excluded.studio_id,
                    "is_active": stmt.excluded.is_active,
                    "updated_at": stmt.excluded.updated_at,
                    "synced_at": stmt.excluded.synced_at,
                },
                where=UserCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, "user.updated")
            await session.commit()

            logger.info(
                "user.updated applied: user_id=%s event_id=%s",
                event["user_id"], event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_user_deactivated(event: Dict[str, Any]) -> None:
    """
    Обработать 'user.deactivated' - soft-delete пользователя в кеше.

    Запись НЕ удаляется, только is_active=false. Если записи ещё нет
    (deactivated пришёл раньше created) - просто пропускаем: создавать
    запись на основе deactivated-события нельзя, в нём нет имени и роли.
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]

    async with CrmAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            existing = await _get_existing(session, user_id)
            if existing is None:
                logger.warning(
                    "user.deactivated for unknown user_id=%s, skipping cache "
                    "update (marking processed)", user_id,
                )
            elif _as_aware(existing.updated_at) < occurred_at:
                existing.is_active = False
                existing.updated_at = occurred_at
                existing.synced_at = datetime.now(timezone.utc)
            else:
                logger.debug(
                    "Stale user.deactivated ignored: user_id=%s "
                    "(cache newer than event)", user_id,
                )

            await _mark_processed(session, event_id, "user.deactivated")
            await session.commit()

            logger.info(
                "user.deactivated applied: user_id=%s event_id=%s",
                user_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )


async def handle_role_changed(event: Dict[str, Any]) -> None:
    """
    Обработать 'role.changed' - обновить роль пользователя в кеше.

    Для CRM роль критична: лид можно назначить только на пользователя
    с ролью admin. Если запись ещё не существует - пропускаем (role.changed
    не несёт имени, создать полноценную запись из него нельзя).
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]

    async with CrmAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug(
                    "Event already processed, skipping: event_id=%s", event_id
                )
                return

            existing = await _get_existing(session, user_id)
            if existing is None:
                logger.warning(
                    "role.changed for unknown user_id=%s, skipping cache "
                    "update (marking processed)", user_id,
                )
            elif _as_aware(existing.updated_at) < occurred_at:
                existing.role_name = event["new_role_name"]
                existing.updated_at = occurred_at
                existing.synced_at = datetime.now(timezone.utc)
            else:
                logger.debug(
                    "Stale role.changed ignored: user_id=%s "
                    "(cache newer than event)", user_id,
                )

            await _mark_processed(session, event_id, "role.changed")
            await session.commit()

            logger.info(
                "role.changed applied: user_id=%s new_role=%s event_id=%s",
                user_id, event.get("new_role_name"), event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: event_id=%s err=%s",
                event_id, exc,
            )