"""
shared.auth_lib — общая библиотека валидации JWT и проверки blacklist.

Используется всеми бекенд-сервисами проекта schedule-platform-plus
для унифицированной аутентификации.
"""

from shared.auth_lib.exceptions import (
    AuthLibException,
    InvalidTokenError,
    TokenRevokedError,
    TokenTypeMismatchError,
)
from shared.auth_lib.schemas import TokenPayload
from shared.auth_lib.jwt_validator import JWTValidator
from shared.auth_lib.blacklist_checker import BlacklistChecker, RedisClientProtocol

__all__ = [
    "AuthLibException",
    "InvalidTokenError",
    "TokenRevokedError",
    "TokenTypeMismatchError",
    "TokenPayload",
    "JWTValidator",
    "BlacklistChecker",
    "RedisClientProtocol",
]