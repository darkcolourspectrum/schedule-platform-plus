"""
Скрипт инициализации базы данных
Создает роли и тестового администратора
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent.parent))

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Импортируем все модели для правильной инициализации SQLAlchemy
from app.models import *
from app.database.connection import create_async_session_factory, test_database_connection
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.core.security import SecurityManager


async def init_roles():
    """Инициализация ролей по умолчанию"""
    session_factory = create_async_session_factory()
    
    async with session_factory() as db:
        role_repo = RoleRepository(db)
        
        print("📋 Создание ролей по умолчанию...")
        await role_repo.create_default_roles()
        
        # Проверим созданные роли
        roles = await role_repo.get_all()
        print(f"✅ Создано ролей: {len(roles)}")
        for role in roles:
            print(f"   - {role.name}: {role.description}")
        
        await db.commit()


async def create_admin_user():
    """Создание администратора по умолчанию"""
    session_factory = create_async_session_factory()
    
    async with session_factory() as db:
        user_repo = UserRepository(db)
        role_repo = RoleRepository(db)
        security = SecurityManager()
        
        # Проверяем, есть ли уже администратор
        existing_admin = await user_repo.get_by_email("admin@example.com")
        if existing_admin:
            print("⚠️  Администратор уже существует")
            return
        
        # Получаем роль администратора
        admin_role = await role_repo.get_admin_role()
        if not admin_role:
            print("❌ Роль администратора не найдена")
            return
        
        # Создаем администратора
        hashed_password = security.hash_password("admin123")
        
        admin_user = await user_repo.create_user(
            email="admin@example.com",
            first_name="Системный",
            last_name="Администратор",
            role_id=admin_role.id,
            hashed_password=hashed_password,
            privacy_policy_accepted=True
        )
        
        print("✅ Создан администратор:")
        print(f"   Email: admin@example.com")
        print(f"   Пароль: admin123")
        print(f"   ID: {admin_user.id}")
        
        await db.commit()


async def main():
    """Главная функция инициализации"""
    print("🚀 Инициализация базы данных для Auth Service")
    print("=" * 50)
    
    # Проверяем подключение к БД
    print("🔄 Проверка подключения к базе данных...")
    if not await test_database_connection():
        print("❌ Не удалось подключиться к базе данных!")
        print("💡 Проверьте настройки в .env файле")
        return False
    
    try:
        # Инициализируем роли
        await init_roles()
        print()
        
        # Создаем администратора
        await create_admin_user()
        print()
        
        print("🎉 Инициализация завершена успешно!")
        print("=" * 50)
        print("💡 Теперь можно запустить приложение:")
        print("   python -m app.main")
        print()
        print("🔑 Данные для входа в систему:")
        print("   Email: admin@example.com")
        print("   Пароль: admin123")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        print(f"📋 Тип ошибки: {type(e).__name__}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)