"""FastAPI-зависимости VK Bot Service."""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db as _get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Сессия БД для HTTP-эндпоинтов."""
    async for session in _get_db():
        yield session
