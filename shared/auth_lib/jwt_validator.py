"""
Валидация JWT-токенов: проверка подписи, срока действия и типа токена.

Этот модуль НЕ проверяет blacklist — только криптографические свойства токена.
Проверка отзыва токена выполняется отдельно в blacklist_checker.py.
"""

import logging
from typing import Optional
from jose import jwt, JWTError, ExpiredSignatureError

from shared.auth_lib.exceptions import (
    InvalidTokenError,
    TokenTypeMismatchError,
)
from shared.auth_lib.schemas import TokenPayload

logger = logging.getLogger(__name__)


class JWTValidator:
    """
    Валидатор JWT-токенов.
    
    Создаётся один раз в каждом сервисе с его JWT-секретом и алгоритмом.
    Все экземпляры в системе должны использовать один и тот же секрет
    (обычно settings.jwt_secret_key из общей переменной окружения).
    """
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        if not secret_key:
            raise ValueError("JWT secret key must not be empty")
        self._secret_key = secret_key
        self._algorithm = algorithm
    
    def decode(
        self,
        token: str,
        expected_type: Optional[str] = "access",
    ) -> TokenPayload:
        """
        Декодировать и проверить JWT-токен.
        
        Проверяет:
            - Формат токена
            - Подпись
            - Срок действия (exp)
            - Тип токена (если задан expected_type)
        
        Args:
            token: Сырая строка JWT-токена.
            expected_type: Ожидаемый тип токена (access/refresh).
                Если None — проверка типа не выполняется.
        
        Returns:
            Распаршенный TokenPayload.
        
        Raises:
            InvalidTokenError: Токен невалиден (формат, подпись, истёк срок).
            TokenTypeMismatchError: Тип токена не соответствует ожидаемому.
        """
        if not token:
            raise InvalidTokenError("Empty token")
        
        try:
            raw_payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except ExpiredSignatureError:
            raise InvalidTokenError("Token expired")
        except JWTError as exc:
            logger.debug("JWT decode error: %s", exc)
            raise InvalidTokenError(f"Invalid token: {exc}")
        
        try:
            payload = TokenPayload(**raw_payload)
        except Exception as exc:
            logger.warning("JWT payload schema validation failed: %s", exc)
            raise InvalidTokenError(f"Malformed token payload: {exc}")
        
        if expected_type is not None and payload.type != expected_type:
            raise TokenTypeMismatchError(
                f"Expected token type '{expected_type}', got '{payload.type}'"
            )
        
        return payload
    
    def decode_safe(
        self,
        token: str,
        expected_type: Optional[str] = "access",
    ) -> Optional[TokenPayload]:
        """
        То же что decode(), но возвращает None вместо исключения.
        Удобно для мест, где нужна простая bool-проверка.
        """
        try:
            return self.decode(token, expected_type=expected_type)
        except (InvalidTokenError, TokenTypeMismatchError):
            return None