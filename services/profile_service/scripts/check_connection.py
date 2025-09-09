"""
Тест подключения к БД и Redis для Profile Service
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
from app.database.connection import test_database_connection, close_database_connections
from app.database.redis_client import redis_client


async def test_all_connections():
    """Тестирование всех подключений"""
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЙ PROFILE SERVICE")
    print("=" * 60)
    
    print(f"Сервис: {settings.app_name} v{settings.app_version}")
    print(f"Окружение: {settings.environment}")
    print(f"Debug режим: {settings.debug}")
    
    # Тест PostgreSQL
    print("\n" + "=" * 40)
    print("ТЕСТИРОВАНИЕ POSTGRESQL")
    print("=" * 40)
    print(f"URL: {settings.database_url_async}")
    print(f"База данных: {settings.database_name}")
    print(f"Пользователь: {settings.database_user}")
    print(f"Хост: {settings.database_host}:{settings.database_port}")
    
    db_success = await test_database_connection()
    
    if db_success:
        print("✅ PostgreSQL подключение работает!")
    else:
        print("❌ Проблемы с PostgreSQL!")
        print("💡 Создайте базу данных:")
        print(f"   CREATE DATABASE {settings.database_name};")
        print(f"   CREATE USER {settings.database_user} WITH PASSWORD '{settings.database_password}';")
        print(f"   GRANT ALL PRIVILEGES ON DATABASE {settings.database_name} TO {settings.database_user};")
    
    # Тест Redis
    print("\n" + "=" * 40)
    print("ТЕСТИРОВАНИЕ REDIS")
    print("=" * 40)
    print(f"URL: {settings.redis_url}")
    print(f"DB: {settings.redis_db}")
    
    try:
        await redis_client.connect()
        redis_success = await redis_client.test_connection()
        
        if redis_success:
            print("✅ Redis подключение работает!")
            
            # Тестируем операции
            print("🧪 Тестирование Redis операций...")
            test_key = "profile_test_key"
            test_data = {"test": "data", "service": "profile"}
            
            # SET
            set_ok = await redis_client.set(test_key, test_data, 30)
            if set_ok:
                print("  ✅ SET операция работает")
                
                # GET
                get_data = await redis_client.get(test_key)
                if get_data == test_data:
                    print("  ✅ GET операция работает")
                    
                    # DELETE
                    del_ok = await redis_client.delete(test_key)
                    if del_ok:
                        print("  ✅ DELETE операция работает")
                        print("  🎉 Все Redis операции успешны!")
                    else:
                        print("  ⚠️ DELETE операция не работает")
                else:
                    print("  ❌ GET вернул неверные данные")
            else:
                print("  ❌ SET операция не работает")
                
        else:
            print("⚠️ Redis недоступен, но сервис может работать без кеширования")
            
    except Exception as e:
        print(f"⚠️ Redis недоступен: {e}")
        print("💡 Это не критично для разработки")
        redis_success = False
    finally:
        await redis_client.disconnect()
    
    # Проверяем настройки Profile Service
    print("\n" + "=" * 40)
    print("НАСТРОЙКИ PROFILE SERVICE")
    print("=" * 40)
    print(f"Папка аватаров: {settings.avatar_upload_full_path}")
    print(f"Макс. размер аватара: {settings.max_avatar_size_mb} МБ")
    print(f"Разрешенные типы изображений: {settings.allowed_image_types}")
    print(f"TTL кэша профилей: {settings.cache_user_profile_ttl} сек")
    print(f"TTL кэша дашбордов: {settings.cache_dashboard_ttl} сек")
    
    # Проверяем папку аватаров
    import os
    avatar_path = settings.avatar_upload_full_path
    if not os.path.exists(avatar_path):
        try:
            os.makedirs(avatar_path, exist_ok=True)
            print(f"✅ Папка аватаров создана: {avatar_path}")
        except Exception as e:
            print(f"❌ Не удалось создать папку аватаров: {e}")
    else:
        print(f"✅ Папка аватаров существует: {avatar_path}")
    
    # Закрываем соединения
    await close_database_connections()
    
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
            print("⚠️ Redis недоступен, но это не критично")
            print("✅ Можно продолжать разработку без кеширования")
        
        print("\n📋 Следующие шаги:")
        print("1. Создайте первую миграцию: alembic revision --autogenerate -m 'Initial tables'")
        print("2. Примените миграции: alembic upgrade head")
        print("3. Запустите сервер: python run_server.py")
        print("4. Откройте документацию: http://localhost:8002/docs")
        
        return True
    else:
        print("❌ Критическая ошибка: база данных недоступна!")
        print("\n🔧 Что нужно исправить:")
        print("1. Проверьте, что PostgreSQL запущен")
        print(f"2. Создайте базу данных: CREATE DATABASE {settings.database_name};")
        print("3. Проверьте настройки подключения в .env")
        print("4. Убедитесь, что пользователь БД имеет права доступа")
        
        return False


if __name__ == "__main__":
    print("🔍 Profile Service - Тест подключений")
    success = asyncio.run(test_all_connections())
    exit(0 if success else 1)