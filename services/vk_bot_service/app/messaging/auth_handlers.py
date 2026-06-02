"""
Обработчики событий из exchange 'auth_events' (Auth Service).

Наполняют users_cache - локальную копию пользователей, по которой бот:
  - определяет роль/имя по vk_id входящего сообщения;
  - резолвит user_id -> vk_id для доставки уведомлений.

События user.created / user.updated несут ПОЛНЫЙ снимок пользователя,
включая vk_id (добавлен в payload событий auth - см. INTEGRATION_NOTES.md,
правка #1). user.deactivated помечает запись неактивной (soft-delete).

Каждый handler:
  1. Проверяет идемпотентность (processed_events).
  2. Применяет upsert/soft-delete к users_cache + пишет processed_events.
  3. Всё в одной транзакции.

Out-of-order защита - на уровне репозитория (сравнение occurred_at с
updated_at): более старое событие не перезаписывает более свежее.

vk_id из payload может отсутствовать (None) - если пользователь не
привязывал VK. Тогда запись создаётся/обновляется без vk_id, и доставка
в VK для этого пользователя невозможна, пока он не привяжет VK (после
чего auth пришлёт user.updated уже с vk_id).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import VkBotAsyncSessionLocal
from app.models.processed_event import ProcessedEvent
from app.models.user_cache import UserCache

logger = logging.getLogger(__name__)


def _parse_occurred_at(event: Dict[str, Any]) -> datetime:
    raw = event["occurred_at"]
    parsed = raw if isinstance(raw, datetime) else datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_vk_id(event: Dict[str, Any]) -> Optional[int]:
    """
    Извлечь vk_id из payload. В auth vk_id хранится как строка (String(50)),
    в кеше бота - как BigInteger (числовой VK id). Приводим к int; если
    пусто или неконвертируемо - None (VK не привязан).
    """
    raw = event.get("vk_id")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Unexpected vk_id format in auth event: %r", raw)
        return None


async def _is_already_processed(session: AsyncSession, event_id: UUID) -> bool:
    result = await session.execute(
        select(ProcessedEvent.event_id).where(ProcessedEvent.event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_processed(
    session: AsyncSession, event_id: UUID, event_type: str
) -> None:
    session.add(ProcessedEvent(event_id=event_id, event_type=event_type))


async def _upsert_user(event: Dict[str, Any], event_type: str) -> None:
    """
    Upsert users_cache из user.created / user.updated.

    vk_id обновляется отдельным выражением: пишем его только при
    конфликте, если он пришёл не-None, чтобы случайное событие без vk_id
    не затёрло уже известный vk_id. При первой вставке vk_id берётся как
    есть (может быть None).
    """
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)
    vk_id = _parse_vk_id(event)

    async with VkBotAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: %s", event_id)
                return

            stmt = pg_insert(UserCache).values(
                id=event["user_id"],
                vk_id=vk_id,
                first_name=event.get("first_name", ""),
                last_name=event.get("last_name", ""),
                role_name=event.get("role_name", "student"),
                studio_id=event.get("studio_id"),
                is_active=event.get("is_active", True),
                updated_at=occurred_at,
                synced_at=datetime.now(timezone.utc),
            )

            # При конфликте обновляем поля только если событие новее.
            # vk_id: coalesce(новый, текущий) - не затираем известный vk_id
            # событием, где vk_id отсутствует (None).
            set_ = {
                "first_name": stmt.excluded.first_name,
                "last_name": stmt.excluded.last_name,
                "role_name": stmt.excluded.role_name,
                "studio_id": stmt.excluded.studio_id,
                "is_active": stmt.excluded.is_active,
                "updated_at": stmt.excluded.updated_at,
                "synced_at": stmt.excluded.synced_at,
                "vk_id": func.coalesce(stmt.excluded.vk_id, UserCache.vk_id),
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_=set_,
                where=UserCache.updated_at < stmt.excluded.updated_at,
            )
            await session.execute(stmt)

            await _mark_processed(session, event_id, event_type)
            await session.commit()

            logger.info(
                "%s applied: user_id=%s vk_id=%s event_id=%s",
                event_type, event["user_id"], vk_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: %s err=%s",
                event_id, exc,
            )


async def handle_user_created(event: Dict[str, Any]) -> None:
    await _upsert_user(event, "user.created")


async def handle_user_updated(event: Dict[str, Any]) -> None:
    await _upsert_user(event, "user.updated")


async def handle_user_deactivated(event: Dict[str, Any]) -> None:
    """Пометить пользователя неактивным (soft-delete)."""
    event_id = UUID(str(event["event_id"]))
    occurred_at = _parse_occurred_at(event)
    user_id = event["user_id"]

    async with VkBotAsyncSessionLocal() as session:
        try:
            if await _is_already_processed(session, event_id):
                logger.debug("Event already processed, skipping: %s", event_id)
                return

            result = await session.execute(
                select(UserCache).where(UserCache.id == user_id)
            )
            user = result.scalar_one_or_none()
            # Применяем только если событие новее текущего состояния.
            if user is not None and (
                user.updated_at is None or user.updated_at < occurred_at
            ):
                user.is_active = False
                user.updated_at = occurred_at
                user.synced_at = datetime.now(timezone.utc)

            await _mark_processed(session, event_id, "user.deactivated")
            await session.commit()

            logger.info(
                "user.deactivated applied: user_id=%s event_id=%s",
                user_id, event_id,
            )
        except IntegrityError as exc:
            await session.rollback()
            logger.debug(
                "Event processed concurrently, skipping: %s err=%s",
                event_id, exc,
            )

