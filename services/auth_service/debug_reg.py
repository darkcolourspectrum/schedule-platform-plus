"""
Скрипт для отладки процесса регистрации
Поможет найти проблему в цепочке регистрации пользователя
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database.connection import create_async_session_factory, test_database_connection
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.core.security import SecurityManager


async def debug_registration():
    """Отладка процесса регистрации"""
    
    print("🔍 Отладка процесса регистрации")
    print("=" * 50)
    
    # Проверяем подключение к БД
    print("1. Проверка подключения к базе данных...")
    if not await test_database_connection():
        print("❌ Проблема с подключением к БД!")
        return False
    print("✅ БД подключена")
    
    session_factory = create_async_session_factory()
    
    async with session_factory() as db:
        try:
            # Проверяем наличие ролей
            print("\n2. Проверка ролей в системе...")
            role_repo = RoleRepository(db)
            roles = await role_repo.get_all()
            
            if not roles:
                print("❌ В системе нет ролей!")
                print("💡 Запустите: python scripts/init_database.py")
                return False
            
            print(f"✅ Найдено ролей: {len(roles)}")
            for role in roles:
                print(f"   - {role.name}: {role.description}")
            
            # Проверяем роль студента по умолчанию
            student_role = await role_repo.get_default_student_role()
            if not student_role:
                print("❌ Не найдена роль студента по умолчанию!")
                return False
            print(f"✅ Роль студента по умолчанию: {student_role.name} (ID: {student_role.id})")
            
            # Тестируем создание пользователя
            print("\n3. Тест создания пользователя...")
            
            test_email = "test_debug@example.com"
            
            # Проверяем, не существует ли уже такой пользователь
            user_repo = UserRepository(db)
            existing_user = await user_repo.get_by_email(test_email)
            if existing_user:
                print(f"⚠️  Пользователь {test_email} уже существует, удаляем...")
                await user_repo.delete(existing_user.id)
            
            # Создаем пользователя через AuthService
            auth_service = AuthService(db)
            
            result = await auth_service.register_user(
                email=test_email,
                password="testpassword123",
                first_name="Test",
                last_name="User",
                phone="+79082119056",
                privacy_policy_accepted=True
            )
            
            print("✅ Пользователь создан успешно!")
            print(f"   ID: {result['user']['id']}")
            print(f"   Email: {result['user']['email']}")
            print(f"   Role: {result['user']['role']}")
            print(f"   Token создан: {'access_token' in result['tokens']}")
            
            # Очистка тестового пользователя
            await user_repo.delete(result['user']['id'])
            print("🗑️  Тестовый пользователь удален")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при отладке: {e}")
            print(f"📋 Тип ошибки: {type(e).__name__}")
            
            # Дополнительная диагностика
            import traceback
            print("\n📋 Полный стек ошибки:")
            traceback.print_exc()
            
            return False


async def check_validation():
    """Проверка валидации входных данных"""
    
    print("\n4. Проверка валидации данных...")
    
    from app.schemas.auth import RegisterRequest
    from pydantic import ValidationError
    
    test_data = {
        "email": "zxczxczxc@example.com",
        "password": "zxczxczxc123",
        "first_name": "string",
        "last_name": "string", 
        "phone": "+79082119056",
        "privacy_policy_accepted": True
    }
    
    try:
        register_request = RegisterRequest(**test_data)
        print("✅ Валидация входных данных прошла успешно")
        print(f"   Email: {register_request.email}")
        print(f"   Password length: {len(register_request.password)}")
        print(f"   Phone: {register_request.phone}")
        print(f"   Privacy accepted: {register_request.privacy_policy_accepted}")
        return True
        
    except ValidationError as e:
        print("❌ Ошибка валидации данных:")
        for error in e.errors():
            print(f"   - {error['loc']}: {error['msg']}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка валидации: {e}")
        return False


async def main():
    """Главная функция отладки"""
    
    # Проверяем валидацию
    validation_ok = await check_validation()
    
    if not validation_ok:
        print("\n❌ Проблема в валидации данных!")
        return False
    
    # Проверяем регистрацию
    registration_ok = await debug_registration()
    
    if registration_ok:
        print("\n🎉 Все проверки пройдены успешно!")
        print("💡 Проблема может быть в:")
        print("   - Конфигурации FastAPI приложения")
        print("   - Миддлварах")
        print("   - Роутинге")
        print("   - Dependency injection")
        return True
    else:
        print("\n❌ Найдены проблемы в процессе регистрации")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)