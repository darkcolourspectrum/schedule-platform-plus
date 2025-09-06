"""
Скрипт для проверки всех подключений Profile Service
Проверяет PostgreSQL, Redis и интеграцию с другими сервисами
"""

import asyncio
import sys
import os
from typing import Dict, Any

# Добавляем путь к приложению
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.config import settings
from app.database.connection import check_database_connection, init_database
from app.database.redis_client import redis_client


async def check_postgresql() -> Dict[str, Any]:
    """Проверка подключения к PostgreSQL"""
    print("\n🐘 Проверка PostgreSQL...")
    print("=" * 40)
    
    try:
        # Проверяем настройки
        print(f"Database URL: {settings.database_url_async}")
        print(f"Database Name: {settings.database_name}")
        print(f"Host: {settings.database_host}:{settings.database_port}")
        
        # Проверяем соединение
        if await check_database_connection():
            print("✅ Подключение к PostgreSQL успешно")
            
            # Пробуем инициализировать таблицы
            try:
                await init_database()
                print("✅ Таблицы базы данных инициализированы")
            except Exception as e:
                print(f"⚠️ Предупреждение при инициализации таблиц: {e}")
            
            return {"status": "success", "message": "PostgreSQL connection OK"}
        else:
            return {"status": "error", "message": "Failed to connect to PostgreSQL"}
            
    except Exception as e:
        print(f"❌ Ошибка PostgreSQL: {e}")
        return {"status": "error", "message": str(e)}


async def check_redis() -> Dict[str, Any]:
    """Проверка подключения к Redis"""
    print("\n🔴 Проверка Redis...")
    print("=" * 40)
    
    try:
        # Проверяем настройки
        print(f"Redis URL: {settings.redis_url}")
        print(f"Redis DB: {settings.redis_db}")
        
        # Подключаемся к Redis
        await redis_client.connect()
        
        if redis_client.is_connected:
            print("✅ Подключение к Redis успешно")
            
            # Тестируем операции
            test_key = "profile_service:connection_test"
            test_data = {"service": "profile", "test": True}
            
            # Запись
            if await redis_client.set(test_key, test_data, ttl=10):
                print("✅ Запись в Redis работает")
            else:
                print("❌ Ошибка записи в Redis")
            
            # Чтение
            result = await redis_client.get(test_key)
            if result and result.get("service") == "profile":
                print("✅ Чтение из Redis работает")
            else:
                print("❌ Ошибка чтения из Redis")
            
            # Удаление
            if await redis_client.delete(test_key):
                print("✅ Удаление из Redis работает")
            
            # Health check
            health = await redis_client.health_check()
            print(f"Redis версия: {health.get('version', 'unknown')}")
            print(f"Использование памяти: {health.get('used_memory', 'unknown')}")
            print(f"Подключенных клиентов: {health.get('connected_clients', 'unknown')}")
            
            await redis_client.disconnect()
            return {"status": "success", "message": "Redis connection OK"}
        else:
            return {"status": "error", "message": "Failed to connect to Redis"}
            
    except Exception as e:
        print(f"❌ Ошибка Redis: {e}")
        return {"status": "error", "message": str(e)}


async def check_auth_service() -> Dict[str, Any]:
    """Проверка доступности Auth Service"""
    print("\n🔐 Проверка Auth Service...")
    print("=" * 40)
    
    try:
        import httpx
        
        print(f"Auth Service URL: {settings.auth_service_url}")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Проверяем health endpoint
            response = await client.get(f"{settings.auth_service_url}/health")
            
            if response.status_code == 200:
                print("✅ Auth Service доступен")
                data = response.json()
                print(f"Сервис: {data.get('service', 'unknown')}")
                print(f"Версия: {data.get('version', 'unknown')}")
                return {"status": "success", "message": "Auth Service is available"}
            else:
                print(f"⚠️ Auth Service отвечает с кодом {response.status_code}")
                return {"status": "warning", "message": f"Auth Service HTTP {response.status_code}"}
                
    except httpx.ConnectError:
        print("❌ Auth Service недоступен (нет соединения)")
        return {"status": "error", "message": "Auth Service connection failed"}
    except httpx.TimeoutException:
        print("❌ Auth Service не отвечает (таймаут)")
        return {"status": "error", "message": "Auth Service timeout"}
    except Exception as e:
        print(f"❌ Ошибка проверки Auth Service: {e}")
        return {"status": "error", "message": str(e)}


async def check_schedule_service() -> Dict[str, Any]:
    """Проверка доступности Schedule Service"""
    print("\n📅 Проверка Schedule Service...")
    print("=" * 40)
    
    try:
        import httpx
        
        print(f"Schedule Service URL: {settings.schedule_service_url}")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Проверяем health endpoint
            response = await client.get(f"{settings.schedule_service_url}/health")
            
            if response.status_code == 200:
                print("✅ Schedule Service доступен")
                data = response.json()
                print(f"Сервис: {data.get('service', 'unknown')}")
                print(f"Версия: {data.get('version', 'unknown')}")
                return {"status": "success", "message": "Schedule Service is available"}
            else:
                print(f"⚠️ Schedule Service отвечает с кодом {response.status_code}")
                return {"status": "warning", "message": f"Schedule Service HTTP {response.status_code}"}
                
    except httpx.ConnectError:
        print("❌ Schedule Service недоступен (нет соединения)")
        return {"status": "error", "message": "Schedule Service connection failed"}
    except httpx.TimeoutException:
        print("❌ Schedule Service не отвечает (таймаут)")
        return {"status": "error", "message": "Schedule Service timeout"}
    except Exception as e:
        print(f"❌ Ошибка проверки Schedule Service: {e}")
        return {"status": "error", "message": str(e)}


async def check_environment() -> Dict[str, Any]:
    """Проверка переменных окружения"""
    print("\n🌍 Проверка окружения...")
    print("=" * 40)
    
    try:
        # Проверяем обязательные переменные
        required_vars = [
            "DATABASE_URL",
            "INTERNAL_API_KEY"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(settings, var.lower(), None):
                missing_vars.append(var)
        
        if missing_vars:
            print(f"❌ Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
            return {"status": "error", "message": f"Missing variables: {missing_vars}"}
        
        print("✅ Все обязательные переменные настроены")
        print(f"Окружение: {settings.environment}")
        print(f"Debug режим: {settings.debug}")
        print(f"Максимальный размер аватара: {settings.max_avatar_size_mb} MB")
        
        return {"status": "success", "message": "Environment configuration OK"}
        
    except Exception as e:
        print(f"❌ Ошибка проверки окружения: {e}")
        return {"status": "error", "message": str(e)}


async def main():
    """Основная функция проверки всех подключений"""
    print("🔍 Profile Service - Проверка подключений")
    print("=" * 50)
    
    # Все проверки
    checks = [
        ("Environment", check_environment()),
        ("PostgreSQL", check_postgresql()),
        ("Redis", check_redis()),
        ("Auth Service", check_auth_service()),
        ("Schedule Service", check_schedule_service())
    ]
    
    results = {}
    
    # Выполняем проверки
    for name, check_coro in checks:
        try:
            result = await check_coro
            results[name] = result
        except Exception as e:
            results[name] = {"status": "error", "message": str(e)}
    
    # Выводим итоги
    print("\n📊 Итоги проверки:")
    print("=" * 50)
    
    success_count = 0
    warning_count = 0
    error_count = 0
    
    for name, result in results.items():
        status = result["status"]
        message = result["message"]
        
        if status == "success":
            print(f"✅ {name}: {message}")
            success_count += 1
        elif status == "warning":
            print(f"⚠️ {name}: {message}")
            warning_count += 1
        else:
            print(f"❌ {name}: {message}")
            error_count += 1
    
    print(f"\nРезультат: {success_count} успешно, {warning_count} предупреждений, {error_count} ошибок")
    
    if error_count == 0:
        print("\n🎉 Все основные компоненты работают!")
        if warning_count > 0:
            print("⚠️ Есть предупреждения, но сервис может работать")
    else:
        print("\n❌ Обнаружены критические ошибки")
        print("💡 Проверьте:")
        print("   1. Запущен ли PostgreSQL")
        print("   2. Запущен ли Redis")
        print("   3. Правильно ли настроен .env файл")
        print("   4. Запущены ли Auth и Schedule сервисы")
    
    return error_count == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)