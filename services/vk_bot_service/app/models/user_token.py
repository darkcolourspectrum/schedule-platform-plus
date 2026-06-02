"""UserToken model - хранение refresh-токена пользователя для действий бота от его имени."""
from typing import Optional

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserToken(Base, TimestampMixin):
    """
    Refresh-токен пользователя платформы, полученный ботом.

    Зачем хранить. Действия преподавателя (отмена занятия, расписание)
    идут в Schedule Service ОТ ИМЕНИ пользователя - с его JWT. Бот
    получает пару токенов через internal vk-login (по доверенному vk_id
    из Long Poll) и хранит здесь refresh-токен. Access-токены коротко-
    живущие и в БД не хранятся: бот обновляет access из refresh через
    POST /api/v1/auth/refresh (этот роут умеет брать refresh из тела -
    сделано в Блоке 1 ровно для бота) и держит access в памяти процесса.

    Один пользователь = одна запись (PK user_id). Повторный vk-login
    перезаписывает refresh-токен (старая сессия бота заменяется новой).

    Безопасность. Это полноценный refresh-токен платформы, поэтому
    таблица чувствительна. Доступ к БД бота ограничен самим сервисом;
    дополнительное шифрование на уровне приложения для MVP не вводим, но
    при ужесточении требований это первый кандидат на доработку.
    """

    __tablename__ = "user_tokens"

    # user_id платформы - первичный ключ.
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # vk_id владельца - для обратного поиска и аудита.
    vk_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # Refresh-токен платформы.
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)

    # Денормализованная роль на момент логина - быстрый ответ на вопрос
    # "что показывать в меню", не дёргая auth. Источник истины - users_cache,
    # это лишь снимок для UX.
    role_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<UserToken(user_id={self.user_id}, vk_id={self.vk_id})>"
