"""
Подключение к PostgreSQL базе данных для Profile Service
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import sys

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings

logger = logging.getLogger(__name__)

# Создание асинхронного движка
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,  # Логирование SQL запросов в dev режиме
    pool_pre_ping=True,   # Проверка соединений
    pool_recycle=3600,    # Переподключение каждый час
    max_overflow=10,      # Дополнительные соединения
    pool_size=20          # Размер пула соединений
)

# Создание фабрики сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False
)


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Получение сессии базы данных для dependency injection
    
    Yields:
        AsyncSession: Сессия SQLAlchemy
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """
    Тестирование подключения к базе данных
    
    Returns:
        bool: True если подключение успешно
    """
    try:
        async with engine.begin() as conn:
            # Простой запрос для проверки соединения
            result = await conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            if test_value == 1:
                logger.info("✅ Подключение к PostgreSQL установлено успешно")
                
                # Проверяем, какая база данных подключена
                db_result = await conn.execute(text("SELECT current_database()"))
                db_name = db_result.scalar()
                logger.info(f"📊 Подключена база данных: {db_name}")
                
                return True
            else:
                logger.error("❌ Тест подключения к базе данных провален")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к базе данных: {e}")
        logger.error(f"URL подключения: {settings.database_url_async}")
        return False


async def close_database_connections():
    """
    Закрытие всех соединений с базой данных
    """
    try:
        await engine.dispose()
        logger.info("🔐 Соединения с базой данных закрыты")
    except Exception as e:
        logger.error(f"Ошибка при закрытии соединений: {e}")


async def create_tables():
    """
    Создание всех таблиц в базе данных
    ВНИМАНИЕ: Используется только для разработки!
    В продакшене используйте Alembic миграции.
    """
    try:
        from app.models.base import Base
        
        async with engine.begin() as conn:
            # Создаем все таблицы
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Все таблицы созданы успешно")
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        raise


async def drop_tables():
    """
    Удаление всех таблиц из базы данных
    ВНИМАНИЕ: Опасная операция! Используется только для разработки!
    """
    try:
        from app.models.base import Base
        
        async with engine.begin() as conn:
            # Удаляем все таблицы
            await conn.run_sync(Base.metadata.drop_all)
            logger.warning("⚠️ Все таблицы удалены")
            
    except Exception as e:
        logger.error(f"❌ Ошибка удаления таблиц: {e}")
        raise


# Алиас для совместимости
get_db = get_database_session


# Для тестирования подключения из командной строки
if __name__ == "__main__":
    async def main():
        print("🔄 Тестирование подключения к базе данных...")
        
        connected = await test_database_connection()
        
        if connected:
            print("✅ Подключение успешно!")
        else:
            print("❌ Подключение не удалось!")
            
        await close_database_connections()
    
    asyncio.run(main())