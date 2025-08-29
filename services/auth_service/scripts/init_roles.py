import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent.parent))

from app.database.connection import AsyncSessionLocal
from app.repositories.role_repository import RoleRepository

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def init_default_roles():
    """Инициализация ролей по умолчанию"""
    
    async with AsyncSessionLocal() as db:
        role_repo = RoleRepository(db)
        
        print("Создание ролей по умолчанию...")
        await role_repo.create_default_roles()
        print("Роли успешно созданы!")
        
        # Проверим созданные роли
        roles = await role_repo.get_all()
        print(f"\nСозданные роли ({len(roles)}):")
        for role in roles:
            print(f"- {role.name}: {role.description}")


if __name__ == "__main__":
    asyncio.run(init_default_roles())