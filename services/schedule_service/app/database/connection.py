"""
Подключение к базе данных и создание асинхронных сессий
"""

import asyncio
import sys
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
import logging

# Исправление для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)

# Глобальные переменные для движка и сессии
async_engine = None
AsyncSessionLocal = None


def create_async_database_engine():
    """Создание асинхронного движка базы данных"""
    global async_engine
    
    if async_engine is None:
        async_engine = create_async_engine(
            settings.database_url_async,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
        )
        logger.info(f"Асинхронный движок БД создан: {settings.database_name}")
    
    return async_engine


def create_async_session_factory():
    """Создание фабрики асинхронных сессий"""
    global AsyncSessionLocal
    
    if AsyncSessionLocal is None:
        engine = create_async_database_engine()
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False
        )
        logger.info("Фабрика асинхронных сессий создана")
    
    return AsyncSessionLocal


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения асинхронной сессии в FastAPI endpoints
    """
    session_factory = create_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка сессии БД: {e}")
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """Тестирование подключения к базе данных"""
    try:
        engine = create_async_database_engine()
        
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            value = result.scalar()
            
            if value == 1:
                logger.info("Подключение к базе данных успешно!")
                
                # Дополнительная информация
                version_result = await conn.execute(text("SELECT version()"))
                version = version_result.scalar()
                logger.info(f"Версия PostgreSQL: {version.split()[1] if version else 'Неизвестно'}")
                
                db_result = await conn.execute(text("SELECT current_database()"))
                current_db = db_result.scalar()
                logger.info(f"Текущая база: {current_db}")
                
                return True
            else:
                logger.error("Неожиданный результат тестового запроса")
                return False
                
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        return False


async def close_database_connections():
    """Закрытие соединений с базой данных"""
    global async_engine
    
    if async_engine:
        await async_engine.dispose()
        logger.info("Соединения с базой данных закрыты")
        async_engine = None


# Инициализация при импорте модуля
def init_database():
    """Инициализация базы данных"""
    create_async_database_engine()
    create_async_session_factory()


if __name__ == "__main__":
    """
    Тестовый скрипт для проверки подключения
    Запуск: python -m app.database.connection
    """
    
    async def main():
        print("Тестирование подключения к PostgreSQL...")
        print(f"URL: {settings.database_url_async}")
        print(f"База: {settings.database_name}")
        print(f"Пользователь: {settings.database_user}")
        print("-" * 50)
        
        result = await test_database_connection()
        
        if result:
            print("\nПодключение работает отлично!")
            print("Можно продолжать разработку!")
        else:
            print("\nПроблемы с подключением")
            print("Проверьте настройки в .env файле")
        
        await close_database_connections()
        return result
    
    success = asyncio.run(main())
    exit(0 if success else 1)