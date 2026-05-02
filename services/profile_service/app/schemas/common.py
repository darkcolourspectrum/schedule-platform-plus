"""
Общие Pydantic схемы для Profile Service
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """Базовая схема успешного ответа"""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Базовая схема ответа с ошибкой"""
    success: bool = False
    error: str
    detail: Optional[str] = None
    error_code: Optional[str] = None