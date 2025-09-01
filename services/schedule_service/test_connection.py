"""
Тест подключения к БД и Redis для Schedule Service
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings
from app.database.connection import test_database_connection
from app.database.redis_client import redis_client


async def test_all_connections():
    """Тестирование всех подключений"""
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЙ SCHEDULE SERVICE")
    print("=" * 60)
    
    print(f"Сервис: {settings.app_name} v{settings.app_version}")
    print(f"Окружение: {settings.environment}")
    print(f"Debug режим: {settings.debug}")
    
    # Тест PostgreSQL
    print("\n" + "=" * 40)
    print("ТЕСТИРОВАНИЕ POSTGRESQL")
    print("=" * 40)
    print(f"URL: {settings.database_url}")
    print(f"База данных: {settings.database_name}")
    print(f"Пользователь: {settings.database_user}")
    
    db_success = await test_database_connection()
    
    if db_success:
        print("✅ PostgreSQL подключение работает!")
    else:
        print("❌ Проблемы с PostgreSQL!")
        print("💡 Создайте базу данных:")
        print(f"   CREATE DATABASE {settings.database_name};")
    
    # Тест Redis
    print("\n" + "=" * 40)
    print("ТЕСТИРОВАНИЕ REDIS")
    print("=" * 40)
    print(f"URL: {settings.redis_url}")
    print(f"DB: {settings.redis_db}")
    
    try:
        redis_success = await redis_client.test_connection()
        if redis_success:
            print("✅ Redis подключение работает!")
        else:
            print("⚠️  Redis недоступен, но сервис может работать без кеширования")
    except Exception as e:
        print(f"⚠️  Redis недоступен: {e}")
        print("💡 Это не критично для разработки")
        redis_success = False
    finally:
        await redis_client.disconnect()
    
    # Итоги
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    if db_success:
        print("✅ База данных готова к работе")
        if redis_success:
            print("✅ Redis готов для кеширования")
            print("🎉 Все системы готовы! Можно приступать к разработке!")
        else:
            print("⚠️  Redis недоступен, но это не критично")
            print("✅ Можно продолжать разработку без кеширования")
        
        print("\n📋 Следующие шаги:")
        print("1. Создайте модели данных")
        print("2. Создайте миграции: alembic revision --autogenerate -m 'Initial migration'")
        print("3. Примените миграции: alembic upgrade head")
        print("4. Запустите сервер: python run_server.py")
        
        return True
    else:
        print("❌ Критическая ошибка: база данных недоступна!")
        print("\n🔧 Что нужно исправить:")
        print("1. Проверьте, что PostgreSQL запущен")
        print(f"2. Создайте базу данных: CREATE DATABASE {settings.database_name};")
        print("3. Проверьте настройки подключения в .env")
        
        return False


if __name__ == "__main__":
    success = asyncio.run(test_all_connections())
    exit(0 if success else 1)