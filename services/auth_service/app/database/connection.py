"""
Тест асинхронного подключения к базе данных
Запуск: python test_async_db.py
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import logging
from app.config import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Исправление для Windows - используем SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def test_async_connection():
    """Тест асинхронного подключения к PostgreSQL с psycopg3"""
    try:
        # Создаем асинхронный движок
        async_engine = create_async_engine(
            settings.database_url_async,
            echo=True,  # Показывать SQL запросы
            pool_pre_ping=True,
            # Убираем server_settings для psycopg3
            connect_args={}
        )
        
        logger.info(f"🔗 Тестируем URL: {settings.database_url_async}")
        
        # Тестируем подключение
        async with async_engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            test_result = result.scalar()
            
            if test_result == 1:
                logger.info("✅ Асинхронное подключение к базе данных успешно!")
                
                # Получаем информацию о базе данных
                version_result = await conn.execute(text("SELECT version()"))
                version = version_result.scalar()
                logger.info(f"📊 Версия PostgreSQL: {version}")
                
                # Текущая база данных
                db_result = await conn.execute(text("SELECT current_database()"))
                current_db = db_result.scalar()
                logger.info(f"🏷️  Текущая база: {current_db}")
                
                # Текущий пользователь
                user_result = await conn.execute(text("SELECT current_user"))
                current_user = user_result.scalar()
                logger.info(f"👤 Пользователь: {current_user}")
                
                # Закрываем движок
                await async_engine.dispose()
                
                return True
            else:
                logger.error("❌ Ошибка: неожиданный результат тестового запроса")
                await async_engine.dispose()
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка асинхронного подключения к базе данных: {e}")
        logger.error(f"📋 Детали ошибки: {type(e).__name__}")
        return False

if __name__ == "__main__":
    print("🔄 Тестирование асинхронного подключения к PostgreSQL...")
    print(f"🔗 URL: {settings.database_url_async}")
    print(f"🏷️  База: {settings.database_name}")
    print(f"👤 Пользователь: {settings.database_user}")
    print("-" * 50)
    
    result = asyncio.run(test_async_connection())
    
    if result:
        print("\n✅ Асинхронное подключение работает отлично!")
        print("🎉 Можно продолжать с созданием моделей!")
    else:
        print("\n❌ Проблемы с асинхронным подключением")
        print("💡 Возможные решения:")
        print("   1. Убедись что psycopg установлен: pip install psycopg")
        print("   2. Проверь что версия psycopg >= 3.0")
        print("   3. Попробуй переустановить: pip uninstall psycopg && pip install psycopg")