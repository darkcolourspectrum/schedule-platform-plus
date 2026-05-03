"""
Подключение к PostgreSQL базе данных для Profile Service.
"""

import asyncio
import logging
import sys
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings

logger = logging.getLogger(__name__)


# Асинхронный движок к PostgreSQL.
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=3600,
    max_overflow=10,
    pool_size=20,
)

# Фабрика сессий. Используется как контекст-менеджер во всех местах,
# где нужна сессия (auth_client, handlers consumer, FastAPI DI).
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False,
)


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency для получения сессии БД в endpoints.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as exc:
            logger.error(f"Database session error: {exc}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """
    Проверка доступности БД при старте приложения.
    Вызывается из lifespan в main.py.
    """
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            if result.scalar() == 1:
                db_result = await conn.execute(text("SELECT current_database()"))
                logger.info(f"Подключена база данных: {db_result.scalar()}")
                return True
            return False
    except Exception as exc:
        logger.error(f"Ошибка подключения к базе данных: {exc}")
        logger.error(f"URL подключения: {settings.database_url_async}")
        return False


# Алиас для совместимости со старыми импортами в endpoints.
get_db = get_database_session