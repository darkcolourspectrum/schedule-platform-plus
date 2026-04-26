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
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency для получения async сессии БД"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """Проверка подключения к БД"""
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        return False


async def close_db_connections() -> None:
    """Закрытие пула соединений"""
    await engine.dispose()