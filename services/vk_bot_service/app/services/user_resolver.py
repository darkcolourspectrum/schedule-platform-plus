"""
UserResolver - сопоставление VK-собеседника с пользователем платформы.

Две задачи:
  1. Входящее сообщение -> кто это. По vk_id (from_id из Long Poll) найти
     запись users_cache: узнать user_id, роль, имя. Если записи нет -
     значит человек написал боту, но на платформе с этим VK аккаунта
     нет (VK не привязан). Это валидная ситуация: бот предложит подать
     заявку, но действий преподавателя/студента не даст.
  2. Доставка уведомления -> по user_id из события расписания найти vk_id
     адресата. Если vk_id неизвестен - уведомление в VK не доставляется
     (остаётся только in-app от notification_service).

Источник связи vk_id<->user_id - события auth (user.created/updated несут
vk_id). Бот НЕ угадывает эту связь сам: vk_id из входящего сообщения мы
доверяем как идентификатору отправителя, но какому user_id он принадлежит,
знает только auth. Поэтому resolve_by_vk_id опирается на кеш, наполненный
событиями auth - это исключает риск выдать доступ к чужому аккаунту.
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_cache import UserCache
from app.repositories.user_cache import UserCacheRepository

logger = logging.getLogger(__name__)


class UserResolver:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserCacheRepository(db)

    async def resolve_by_vk_id(self, vk_id: int) -> Optional[UserCache]:
        """
        Найти пользователя платформы по vk_id.

        Returns:
            UserCache, если VK привязан к аккаунту (известно из событий
            auth); None - если такого соответствия нет.
        """
        user = await self.users.get_by_vk_id(vk_id)
        if user is None:
            logger.debug("vk_id=%s not resolved to a platform user", vk_id)
        return user

    async def get_vk_id_for_user(self, user_id: int) -> Optional[int]:
        """
        Получить vk_id пользователя для доставки уведомления.

        Returns:
            vk_id, если он известен боту (пользователь привязал VK и
            событие auth донесло это в кеш, либо vk_id уже был проставлен);
            None - vk_id неизвестен, уведомление в VK доставить нельзя
            (останется только in-app уведомление от notification_service).
        """
        user = await self.users.get_by_user_id(user_id)
        if user is None or user.vk_id is None:
            return None
        return user.vk_id

    def is_teacher(self, user: UserCache) -> bool:
        return user.role_name == "teacher"

    def is_admin(self, user: UserCache) -> bool:
        return user.role_name == "admin"

    def is_student(self, user: UserCache) -> bool:
        return user.role_name == "student"
