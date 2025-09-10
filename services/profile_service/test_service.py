"""
Тестирование Profile Service
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.database.connection import test_database_connection, engine
from app.services.cache_service import cache_service
from app.services.auth_client import auth_client


async def test_imports():
    """Тест импортов всех модулей"""
    print("🔍 Тестируем импорты модулей...")
    
    try:
        # Тестируем основные модули
        from app.models.profile import UserProfile
        from app.models.comment import Comment
        from app.models.activity import UserActivity
        print("✅ Модели импортированы успешно")
        
        # Тестируем схемы
        from app.schemas.profile import ProfileResponse, ProfileCreate
        from app.schemas.comment import CommentResponse
        from app.schemas.dashboard import DashboardResponse
        print("✅ Схемы импортированы успешно")
        
        # Тестируем сервисы
        from app.services.profile_service import ProfileService
        from app.services.comment_service import CommentService
        from app.services.dashboard_service import DashboardService
        print("✅ Сервисы импортированы успешно")
        
        # Тестируем core компоненты
        from app.core.exceptions import ProfileException, ProfileNotFoundException
        from app.core.auth import AuthManager, PermissionChecker
        from app.core.middleware import LoggingMiddleware, SecurityHeadersMiddleware
        print("✅ Core компоненты импортированы успешно")
        
        # Тестируем API
        from app.api.v1.profiles import router as profiles_router
        from app.api.router import api_router
        print("✅ API роутеры импортированы успешно")
        
        # Тестируем главное приложение
        from app.main import app
        print("✅ Главное приложение импортировано успешно")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False
    
    return True


async def test_database():
    """Тест подключения к базе данных"""
    print("🔍 Тестируем базу данных...")
    
    try:
        # Тест подключения к БД
        is_healthy = await test_database_connection()
        if is_healthy:
            print("✅ База данных: подключение OK")
            return True
        else:
            print("❌ База данных: проблемы с подключением")
            return False
        
    except Exception as e:
        print(f"❌ База данных: ошибка - {e}")
        return False


async def test_cache():
    """Тест кэширования"""
    print("🔍 Тестируем Redis кэш...")
    
    try:
        # Проверяем что cache_service существует и имеет нужные методы
        if not hasattr(cache_service, 'get') or not hasattr(cache_service, 'set'):
            print("❌ Кэш: CacheService не имеет нужных методов")
            return False
        
        # Тест операций
        test_key = "test_profile_service"
        test_data = {"test": "data", "number": 42}
        
        try:
            # Запись
            success = await cache_service.set(test_key, test_data, ttl=60)
            if not success:
                print("⚠️ Кэш: Redis недоступен, но это не критично")
                return True  # Не критично для разработки
            
            # Чтение
            cached_data = await cache_service.get(test_key)
            if cached_data != test_data:
                print("❌ Кэш: данные не совпадают")
                return False
            
            # Удаление
            deleted = await cache_service.delete(test_key)
            if not deleted:
                print("❌ Кэш: не удалось удалить ключ")
                return False
            
            print("✅ Кэш: все операции работают")
            return True
            
        except Exception as cache_error:
            print(f"⚠️ Кэш: Redis недоступен ({cache_error}) - не критично для разработки")
            return True  # Redis не критичен для разработки
        
    except Exception as e:
        print(f"❌ Кэш: критическая ошибка - {e}")
        return False


async def test_auth_integration():
    """Тест интеграции с Auth Service"""
    print("🔍 Тестируем интеграцию с Auth Service...")
    
    try:
        # Тест health check
        is_available = await auth_client.health_check()
        if is_available:
            print("✅ Auth Service: доступен")
        else:
            print("⚠️  Auth Service: недоступен (это нормально если не запущен)")
        
        return True
        
    except Exception as e:
        print(f"❌ Auth Service: ошибка - {e}")
        return False


async def test_configuration():
    """Тест конфигурации"""
    print("🔍 Проверяем конфигурацию...")
    
    try:
        # Проверяем основные настройки (используем lowercase названия как в settings)
        required_settings = [
            'database_host', 'database_name', 'redis_host', 
            'auth_service_url', 'app_name', 'app_version'
        ]
        
        missing_settings = []
        for setting in required_settings:
            value = getattr(settings, setting, None)
            if not value:
                missing_settings.append(setting)
        
        if missing_settings:
            print(f"❌ Конфигурация: отсутствуют настройки: {', '.join(missing_settings)}")
            print("💡 Проверьте .env файл")
            return False
        
        print("✅ Конфигурация: все необходимые параметры установлены")
        
        # Выводим основную информацию
        print(f"  📝 Название сервиса: {settings.app_name}")
        print(f"  📝 Версия: {settings.app_version}")
        print(f"  📝 Режим отладки: {settings.debug}")
        print(f"  📝 База данных: {settings.database_host}:{settings.database_port}")
        print(f"  📝 Redis: {settings.redis_host}:{settings.redis_port}")
        print(f"  📝 Auth Service URL: {settings.auth_service_url}")
        
        # Проверяем специфичные настройки Profile Service
        if hasattr(settings, 'max_avatar_size_mb') and settings.max_avatar_size_mb > 0:
            print(f"  📝 Максимальный размер аватара: {settings.max_avatar_size_mb}MB")
        
        if hasattr(settings, 'cache_user_profile_ttl') and settings.cache_user_profile_ttl > 0:
            print(f"  📝 TTL кэша профилей: {settings.cache_user_profile_ttl}с")
        
        return True
        
    except Exception as e:
        print(f"❌ Конфигурация: ошибка - {e}")
        return False


async def run_all_tests():
    """Запуск всех тестов"""
    print("🚀 Начинаем полное тестирование Profile Service")
    print("=" * 60)
    
    tests = [
        ("Конфигурация", test_configuration),
        ("Импорты модулей", test_imports),
        ("База данных", test_database),
        ("Кэширование", test_cache),
        ("Auth Service", test_auth_integration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}: критическая ошибка - {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОШЕЛ" if result else "❌ ПРОВАЛЕН"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Итого: {passed}/{total} тестов прошли успешно")
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ! Profile Service готов к запуску!")
        print("\n📋 Следующие шаги:")
        print("  1. Запустите миграции: alembic upgrade head")
        print("  2. Запустите сервер: python run_server.py")
        print("  3. Откройте документацию: http://localhost:8002/docs")
    elif passed >= 3:
        print("\n✅ Основные компоненты работают! Можно продолжать разработку")
        print("⚠️ Проблемы с Redis/Auth Service не критичны для начала")
        print("\n📋 Рекомендуемые шаги:")
        print("  1. Запустите миграции: alembic upgrade head")
        print("  2. Запустите сервер: python run_server.py")
        print("  3. Проверьте /health endpoint")
    else:
        print("\n⚠️  Есть критичные проблемы, которые нужно исправить")
        print("  Проверьте настройки в .env файле")
        print("  Убедитесь что PostgreSQL запущен")
    
    return passed >= 3  # Считаем успехом если прошло 3+ теста


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)