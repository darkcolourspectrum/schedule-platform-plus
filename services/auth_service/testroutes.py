"""
Тест маршрутов FastAPI приложения
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def test_app_creation():
    """Тест создания FastAPI приложения"""
    
    print("🌐 Тестирование создания FastAPI приложения...")
    print("=" * 45)
    
    try:
        from app.main import app
        print("✅ FastAPI приложение создано")
        
        # Проверяем маршруты
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                for method in route.methods:
                    if method != 'HEAD':  # Исключаем HEAD запросы
                        routes.append(f"{method} {route.path}")
        
        print(f"✅ Всего маршрутов: {len(routes)}")
        
        # Ищем маршруты аутентификации
        auth_routes = [r for r in routes if '/auth' in r]
        print(f"✅ Auth маршрутов: {len(auth_routes)}")
        
        if auth_routes:
            print("📋 Найденные auth маршруты:")
            for route in sorted(auth_routes):
                print(f"   - {route}")
        
        # Проверяем конкретный маршрут регистрации
        register_route = "POST /api/v1/auth/register"
        if register_route in routes:
            print(f"✅ Маршрут регистрации найден: {register_route}")
        else:
            print(f"❌ Маршрут регистрации НЕ найден: {register_route}")
            print("📋 Возможные причины:")
            print("   - Роутер не подключен")
            print("   - Неправильный префикс")
            print("   - Ошибка в импортах")
        
        return len(auth_routes) > 0
        
    except Exception as e:
        print(f"❌ Ошибка создания приложения: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_auth_endpoint_details():
    """Детальная проверка auth endpoint"""
    
    print("\n🔍 Детальная проверка auth endpoint...")
    print("=" * 40)
    
    try:
        from app.api.v1.auth import router as auth_router
        print("✅ Auth роутер импортирован")
        
        # Проверяем маршруты в роутере
        routes = []
        for route in auth_router.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                for method in route.methods:
                    if method != 'HEAD':
                        routes.append(f"{method} {route.path}")
        
        print(f"✅ Маршрутов в auth роутере: {len(routes)}")
        print("📋 Маршруты auth роутера:")
        for route in sorted(routes):
            print(f"   - {route}")
        
        # Проверяем конкретные endpoints
        expected_routes = [
            "POST /auth/register",
            "POST /auth/login", 
            "POST /auth/refresh",
            "POST /auth/logout",
            "GET /auth/me"
        ]
        
        print(f"\n🎯 Проверка ожидаемых маршрутов:")
        all_found = True
        for expected in expected_routes:
            if expected in routes:
                print(f"✅ {expected}")
            else:
                print(f"❌ {expected}")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"❌ Ошибка проверки auth роутера: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dependencies():
    """Тест зависимостей"""
    
    print("\n📦 Тестирование зависимостей...")
    print("=" * 35)
    
    try:
        from app.dependencies import get_auth_service, get_current_user
        print("✅ Dependencies импортированы")
        
        from app.services.auth_service import AuthService
        print("✅ AuthService импортирован")
        
        from app.schemas.auth import RegisterRequest, AuthResponse
        print("✅ Auth схемы импортированы")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта зависимостей: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Главная функция тестирования"""
    
    print("🧪 Тестирование FastAPI приложения")
    print("=" * 40)
    
    deps_ok = test_dependencies()
    if not deps_ok:
        print("\n❌ Проблемы с зависимостями!")
        return False
    
    auth_ok = test_auth_endpoint_details()
    if not auth_ok:
        print("\n❌ Проблемы с auth роутером!")
        return False
    
    app_ok = test_app_creation()
    if not app_ok:
        print("\n❌ Проблемы с FastAPI приложением!")
        return False
    
    print("\n🎉 Все тесты маршрутов пройдены!")
    print("💡 Теперь попробуйте:")
    print("   1. Обновить зависимости: pip install -r requirements.txt")
    print("   2. Запустить сервер: python run_server.py") 
    print("   3. Открыть Swagger: http://localhost:8000/docs")
    print("   4. Попробовать регистрацию снова")
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)