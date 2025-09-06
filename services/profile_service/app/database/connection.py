"""
Database connection configuration for Profile Service
Настройка подключения к PostgreSQL с использованием SQLAlchemy 2.0
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, text

from app.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy engine для асинхронных операций
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,  # Логирование SQL запросов в debug режиме
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,   # Переподключение каждый час
)

# Session maker для создания сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии базы данных
    Используется в FastAPI endpoints через Depends()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database():
    """
    Инициализация базы данных
    Создает все таблицы если их нет
    """
    try:
        # Импортируем все модели для создания таблиц
        from app.models import Base
        
        async with engine.begin() as conn:
            # Создаем все таблицы
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
            
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


async def check_database_connection() -> bool:
    """
    Проверка соединения с базой данных
    Возвращает True если соединение успешно
    """
    try:
        async with engine.begin() as conn:
            # Простой запрос для проверки соединения
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()
            
        logger.info("Database connection check: SUCCESS")
        return True
        
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def close_database():
    """Закрытие соединения с базой данных"""
    try:
        await engine.dispose()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database connection: {e}")


# Event listeners для логирования
@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Обработчик подключения к БД"""
    if settings.debug:
        logger.debug("Database connection established")


@event.listens_for(engine.sync_engine, "checkout")
def on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Обработчик взятия соединения из пула"""
    if settings.debug:
        logger.debug("Database connection checked out from pool")


@event.listens_for(engine.sync_engine, "checkin")
def on_checkin(dbapi_connection, connection_record):
    """Обработчик возврата соединения в пул"""
    if settings.debug:
        logger.debug("Database connection returned to pool")


# Вспомогательные функции для тестирования
async def reset_database():
    """
    Сброс базы данных (только для тестов!)
    ОСТОРОЖНО: Удаляет все данные!
    """
    if not settings.is_development:
        raise RuntimeError("Database reset is only allowed in development environment")
    
    try:
        from app.models import Base
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            logger.warning("Database has been reset (all data lost)")
            
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise


if __name__ == "__main__":
    """Скрипт для проверки подключения к БД"""
    import asyncio
    
    async def main():
        print("🔍 Проверка подключения к базе данных...")
        
        if await check_database_connection():
            print("✅ Подключение к базе данных успешно")
        else:
            print("❌ Ошибка подключения к базе данных")
            return
        
        print("🏗️ Инициализация таблиц...")
        try:
            await init_database()
            print("✅ Таблицы созданы успешно")
        except Exception as e:
            print(f"❌ Ошибка создания таблиц: {e}")
        
        await close_database()
        print("🎉 Проверка завершена")
    
    asyncio.run(main())