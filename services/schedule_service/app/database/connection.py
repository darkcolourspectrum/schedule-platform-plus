"""
Database connections for Schedule Service.

Schedule Service использует только собственную БД (READ-WRITE).
Данные из Auth Service приходят через события в exchange 'auth_events'
и хранятся в локальной таблице users_cache.
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


# ==================== SCHEDULE SERVICE DATABASE ====================

schedule_engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

ScheduleAsyncSessionLocal = async_sessionmaker(
    schedule_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_schedule_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии Schedule Service БД.
    Используется в endpoints для работы с расписанием.
    """
    async with ScheduleAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


# Алиасы для совместимости
get_async_session = get_schedule_db
get_db = get_schedule_db


# ==================== HEALTH CHECKS ====================

async def check_database_connection() -> bool:
    """Проверка подключения к Schedule БД."""
    try:
        async with ScheduleAsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False