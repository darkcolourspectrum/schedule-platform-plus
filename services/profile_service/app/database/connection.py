"""
Модуль для подключения к базе данных PostgreSQL
Обеспечивает создание и управление подключениями к БД для Profile Service
"""

import logging
from typing import AsyncGenerator
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import QueuePool

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy"""
    pass


class DatabaseManager:
    """Менеджер для управления подключениями к базе данных"""
    
    def __init__(self):
        self._engine = None
        self._async_engine = None
        self._session_factory = None
        self._async_session_factory = None
    
    def _create_database_url(self) -> tuple[str, str]:
        """Создание URL для синхронной и асинхронной БД"""
        sync_url = settings.database_url
        # Преобразование postgresql:// в postgresql+asyncpg:// для async
        async_url = sync_url.replace('postgresql://', 'postgresql+asyncpg://')
        return sync_url, async_url
    
    @property
    def engine(self):
        """Получение синхронного движка БД"""
        if self._engine is None:
            sync_url, _ = self._create_database_url()
            self._engine = create_engine(
                sync_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=settings.debug
            )
            logger.info("Синхронный движок БД создан")
        return self._engine
    
    @property
    def async_engine(self):
        """Получение асинхронного движка БД"""
        if self._async_engine is None:
            _, async_url = self._create_database_url()
            self._async_engine = create_async_engine(
                async_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=settings.debug
            )
            logger.info("Асинхронный движок БД создан")
        return self._async_engine
    
    @property
    def session_factory(self):
        """Фабрика для создания синхронных сессий"""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                expire_on_commit=False
            )
        return self._session_factory
    
    @property
    def async_session_factory(self):
        """Фабрика для создания асинхронных сессий"""
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._async_session_factory
    
    async def create_tables(self):
        """Создание всех таблиц в базе данных"""
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Все таблицы созданы")
    
    async def drop_tables(self):
        """Удаление всех таблиц из базы данных"""
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            logger.warning("Все таблицы удалены")
    
    async def check_connection(self) -> bool:
        """Проверка подключения к базе данных"""
        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            return False
    
    async def get_database_info(self) -> dict:
        """Получение информации о базе данных"""
        try:
            async with self.async_engine.begin() as conn:
                # Версия PostgreSQL
                version_result = await conn.execute(text("SELECT version()"))
                version = version_result.scalar()
                
                # Название базы данных
                db_name_result = await conn.execute(text("SELECT current_database()"))
                db_name = db_name_result.scalar()
                
                # Количество подключений
                connections_result = await conn.execute(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                ))
                connections = connections_result.scalar()
                
                return {
                    "version": version,
                    "database_name": db_name,
                    "active_connections": connections,
                    "status": "connected"
                }
        except Exception as e:
            logger.error(f"Ошибка получения информации о БД: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def close(self):
        """Закрытие всех подключений к БД"""
        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("Асинхронные подключения к БД закрыты")
        
        if self._engine:
            self._engine.dispose()
            logger.info("Синхронные подключения к БД закрыты")


# Создание глобального экземпляра менеджера БД
db_manager = DatabaseManager()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения асинхронной сессии БД
    Используется в FastAPI endpoints через Depends()
    """
    async with db_manager.async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка в сессии БД: {e}")
            raise
        finally:
            await session.close()


def get_session():
    """
    Получение синхронной сессии БД
    Используется для миграций и синхронных операций
    """
    with db_manager.session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка в синхронной сессии БД: {e}")
            raise
        finally:
            session.close()


# Алиасы для удобства импорта
get_db = get_async_session
async_session_factory = db_manager.async_session_factory
engine = db_manager.engine
async_engine = db_manager.async_engine


if __name__ == "__main__":
    """Тестирование подключения к БД"""
    import asyncio
    
    async def test_connection():
        """Тест подключения к базе данных"""
        print("Тестирование подключения к базе данных Profile Service...")
        
        # Проверка подключения
        is_connected = await db_manager.check_connection()
        print(f"Статус подключения: {'✓ Подключено' if is_connected else '✗ Ошибка подключения'}")
        
        if is_connected:
            # Получение информации о БД
            db_info = await db_manager.get_database_info()
            print(f"База данных: {db_info.get('database_name')}")
            print(f"Активные подключения: {db_info.get('active_connections')}")
            print(f"Версия PostgreSQL: {db_info.get('version', '')[:50]}...")
        
        await db_manager.close()
    
    asyncio.run(test_connection())