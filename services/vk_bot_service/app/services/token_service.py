"""
TokenService - управление токенами платформы для действий бота от имени
пользователя.

Действия преподавателя (отмена занятия, расписание) идут в Schedule
Service с JWT пользователя. Этот сервис добывает и поддерживает токены:

  - get_access_token(user_id, vk_id): вернуть валидный access-токен.
    Стратегия:
      1. Если есть refresh в user_tokens - попробовать обновить access
         через auth /refresh (refresh из тела).
      2. Если refresh нет или он недействителен (401) - выполнить
         internal vk-login по vk_id, сохранить новый refresh, вернуть
         свежий access.
      3. Если vk-login вернул 404 (нет аккаунта с таким vk_id) - вернуть
         None: человек пишет боту, но VK не привязан к платформе.

Access-токены не хранятся в БД (короткоживущие) - сервис возвращает их
вызывающему коду, который держит токен в памяти на время операции.
Refresh-токены хранятся в user_tokens (UserTokenRepository).
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.auth_client import auth_client
from app.repositories.user_token import UserTokenRepository

logger = logging.getLogger(__name__)


class TokenService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tokens = UserTokenRepository(db)

    async def get_access_token(self, user_id: int, vk_id: int) -> Optional[str]:
        """
        Получить валидный access-токен пользователя.

        Returns:
            access_token (str) при успехе; None, если по vk_id нет аккаунта
            на платформе (тогда действий преподавателя/студента бот не даёт).
        """
        # 1. Пытаемся обновить access по сохранённому refresh.
        existing = await self.tokens.get_by_user_id(user_id)
        if existing is not None:
            access = await auth_client.refresh_access_token(existing.refresh_token)
            if access:
                return access
            logger.info(
                "Refresh token invalid for user_id=%s, re-logging via vk-login",
                user_id,
            )

        # 2. Refresh нет или протух - логинимся заново по доверенному vk_id.
        return await self._vk_login_and_store(vk_id)

    async def _vk_login_and_store(self, vk_id: int) -> Optional[str]:
        """
        Выполнить internal vk-login, сохранить refresh, вернуть access.

        Returns:
            access_token или None, если по vk_id нет аккаунта (404).
        """
        result = await auth_client.internal_vk_login(vk_id)
        if result is None:
            return None

        user = result.get("user", {})
        tokens = result.get("tokens", {})
        user_id = user.get("id")
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        role_name = user.get("role")

        if not (user_id and access_token and refresh_token):
            logger.error("vk-login returned incomplete data for vk_id=%s", vk_id)
            return None

        await self.tokens.upsert(
            user_id=user_id,
            vk_id=vk_id,
            refresh_token=refresh_token,
            role_name=role_name,
        )
        return access_token
