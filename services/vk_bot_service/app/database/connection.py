"""Database connection and session management for VK Bot Service."""
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)


# Async engine. database_url_async гарантирует драйвер asyncpg.
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


# Фабрика async-сессий. Именована VkBotAsyncSessionLocal по аналогии с
# CrmAsyncSessionLocal / ScheduleAsyncSessionLocal в других сервисах -
# используется фоновыми воркерами (Long Poll, consumer, outbound retry),
# у которых нет FastAPI-зависимости get_db.
VkBotAsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency для получения async-сессии БД."""
    async with VkBotAsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """Проверка подключения к БД (для health-check и lifespan)."""
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
