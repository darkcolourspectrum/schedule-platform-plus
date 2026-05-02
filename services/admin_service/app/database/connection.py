"""
Database connections for Admin Service.

Admin Service использует только собственную БД (READ-WRITE).
Данные пользователей синхронизируются из Auth Service через события
и хранятся локально в users_cache.
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)


# ==================== ADMIN SERVICE DATABASE ====================

admin_engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AdminAsyncSessionLocal = async_sessionmaker(
    admin_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения сессии Admin Service БД."""
    async with AdminAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


# Алиас для совместимости
get_async_session = get_admin_db


# ==================== HEALTH CHECKS ====================

async def test_admin_db_connection() -> bool:
    """Проверка подключения к Admin Service БД."""
    try:
        async with AdminAsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Admin DB connection test failed: {e}")
        return False


async def close_db_connections():
    """Закрытие всех подключений к БД."""
    await admin_engine.dispose()
    logger.info("All database connections closed")