"""Database connection and session management"""
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from app.config import settings

logger = logging.getLogger(__name__)


# Async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


# Фабрика async-сессий. Именована CrmAsyncSessionLocal по аналогии с
# ScheduleAsyncSessionLocal / AdminAsyncSessionLocal в других сервисах -
# используется фоновыми воркерами и consumer'ами, у которых нет
# FastAPI-зависимости get_db.
CrmAsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency для получения async-сессии БД."""
    async with CrmAsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """Проверка подключения к БД (для health-check)."""
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        return False


async def close_db_connections() -> None:
    """Закрытие пула соединений при остановке сервиса."""
    await engine.dispose()