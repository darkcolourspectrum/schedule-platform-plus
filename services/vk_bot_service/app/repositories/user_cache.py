"""Репозиторий для users_cache."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_cache import UserCache

logger = logging.getLogger(__name__)


class UserCacheRepository:
    """
    Доступ к локальной read-копии пользователей.

    Методы делают flush, но НЕ commit - границей транзакции управляет
    вызывающий сервис (паттерн Unit of Work, как в остальных сервисах).
    Исключение - upsert-методы из consumer'ов, которые коммитят сами
    (см. messaging/auth_handlers.py), потому что у них своя короткая
    транзакция на событие.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user_id(self, user_id: int) -> Optional[UserCache]:
        result = await self.db.execute(
            select(UserCache).where(UserCache.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_vk_id(self, vk_id: int) -> Optional[UserCache]:
        result = await self.db.execute(
            select(UserCache).where(UserCache.vk_id == vk_id)
        )
        return result.scalar_one_or_none()

    async def set_vk_id(self, user_id: int, vk_id: int) -> Optional[UserCache]:
        """
        Привязать vk_id к записи кеша (узнали из Long Poll или дозапроса).

        Не коммитит. Возвращает обновлённую запись или None, если записи
        с таким user_id ещё нет в кеше.
        """
        user = await self.get_by_user_id(user_id)
        if user is None:
            return None
        user.vk_id = vk_id
        user.synced_at = datetime.now(timezone.utc)
        await self.db.flush()
        return user

    async def upsert_from_event(
        self,
        *,
        user_id: int,
        first_name: str,
        last_name: str,
        role_name: str,
        studio_id: Optional[int],
        is_active: bool,
        occurred_at: datetime,
    ) -> None:
        """
        Upsert записи из события auth (user.created/updated).

        Не трогает vk_id: он узнаётся ботом отдельно (из Long Poll) и не
        приходит в событиях auth. ON CONFLICT обновляет поля только если
        событие новее текущего состояния (out-of-order защита по updated_at).

        Не коммитит - коммит делает обработчик события вместе с записью
        в processed_events (одна транзакция на событие).
        """
        stmt = pg_insert(UserCache).values(
            id=user_id,
            first_name=first_name,
            last_name=last_name,
            role_name=role_name,
            studio_id=studio_id,
            is_active=is_active,
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
        await self.db.execute(stmt)

    async def set_inactive(self, user_id: int, occurred_at: datetime) -> None:
        """
        Пометить пользователя неактивным (user.deactivated).

        Soft-delete: запись не удаляется (на неё могут ссылаться
        outbound_messages по user_id для аудита). Только если событие
        новее текущего состояния.
        """
        user = await self.get_by_user_id(user_id)
        if user is None:
            return
        if user.updated_at and user.updated_at >= occurred_at:
            return
        user.is_active = False
        user.updated_at = occurred_at
        user.synced_at = datetime.now(timezone.utc)
        await self.db.flush()
