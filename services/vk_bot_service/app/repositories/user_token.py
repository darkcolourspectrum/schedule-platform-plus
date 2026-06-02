"""Репозиторий для user_tokens."""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_token import UserToken

logger = logging.getLogger(__name__)


class UserTokenRepository:
    """
    Доступ к refresh-токенам пользователей.

    Методы коммитят сами: получение/обновление токена - самостоятельная
    операция в рамках обработки сообщения, вне общей бизнес-транзакции.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user_id(self, user_id: int) -> Optional[UserToken]:
        result = await self.db.execute(
            select(UserToken).where(UserToken.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: int,
        vk_id: int,
        refresh_token: str,
        role_name: Optional[str] = None,
    ) -> None:
        """Сохранить/обновить refresh-токен пользователя. Upsert по user_id."""
        stmt = pg_insert(UserToken).values(
            user_id=user_id,
            vk_id=vk_id,
            refresh_token=refresh_token,
            role_name=role_name,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "vk_id": stmt.excluded.vk_id,
                "refresh_token": stmt.excluded.refresh_token,
                "role_name": stmt.excluded.role_name,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
