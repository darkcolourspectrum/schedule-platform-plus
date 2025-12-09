"""
Database connections for Admin Service

Две базы данных:
1. Admin Service БД - для Studios, Classrooms (READ-WRITE)
2. Auth Service БД - для Users (READ-ONLY)
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)

# ==================== ADMIN SERVICE DATABASE ====================

# Движок для Admin Service БД (READ-WRITE)
admin_engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Session factory для Admin DB
AdminAsyncSessionLocal = async_sessionmaker(
    admin_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии Admin Service БД
    Используется в endpoints для CRUD Studios и Classrooms
    """
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
            logger.error(f"Auth database session error: {e}")
            raise
        finally:
            await session.close()


# ==================== DATABASE HEALTH CHECKS ====================

async def test_admin_db_connection() -> bool:
    """Проверка подключения к Admin Service БД"""
    try:
        async with AdminAsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Admin DB connection test failed: {e}")
        return False


async def test_auth_db_connection() -> bool:
    """Проверка подключения к Auth Service БД"""
    try:
        async with AuthAsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Auth DB connection test failed: {e}")
        return False


async def close_db_connections():
    """Закрытие всех подключений к БД"""
    await admin_engine.dispose()
    await auth_engine.dispose()
    logger.info("All database connections closed")
