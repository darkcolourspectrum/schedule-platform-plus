"""
Кастомные исключения для Profile Service
"""

from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class ProfileException(HTTPException):
    """Базовое исключение для Profile Service"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class RateLimitException(ProfileException):
    """Превышен лимит запросов"""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds",
            headers={"Retry-After": str(retry_after)}
        )