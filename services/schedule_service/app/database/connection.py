"""
Database connections for Schedule Service

Две базы данных:
1. Schedule Service БД - для Lessons, Patterns (READ-WRITE)
2. Auth Service БД - для Users (READ-ONLY)
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)

from app.config import settings

logger = logging.getLogger(__name__)

# ==================== SCHEDULE SERVICE DATABASE ====================

# Движок для Schedule Service БД (READ-WRITE)
schedule_engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Session factory для Schedule DB
ScheduleAsyncSessionLocal = async_sessionmaker(
    schedule_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_schedule_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии Schedule Service БД
    Используется в endpoints для работы с расписанием
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


# Алиас для совместимости
get_async_session = get_schedule_db
get_db = get_schedule_db


# ==================== AUTH SERVICE DATABASE (READ-ONLY) ====================

# Движок для Auth Service БД (READ-ONLY)
auth_engine = create_async_engine(
    settings.auth_db_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# Session factory для Auth DB (READ-ONLY)
AuthAsyncSessionLocal = async_sessionmaker(
    auth_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_auth_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии Auth Service БД (READ-ONLY)
    
    ВАЖНО: Используется ТОЛЬКО для чтения User данных!
    НЕ МОДИФИЦИРОВАТЬ Users через эту сессию!
    """
    async with AuthAsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Auth DB session error: {e}")
            raise
        finally:
            await session.close()


# ==================== DATABASE HEALTHCHECK ====================

async def check_database_connection() -> bool:
    """Проверка подключения к Schedule БД"""
    try:
        async with ScheduleAsyncSessionLocal() as session:
            await session.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def check_auth_database_connection() -> bool:
    """Проверка подключения к Auth БД"""
    try:
        async with AuthAsyncSessionLocal() as session:
            await session.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Auth database connection check failed: {e}")
        return False
