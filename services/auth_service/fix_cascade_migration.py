"""
Скрипт для исправления cascade delete в существующей БД
Выполните этот скрипт один раз для исправления foreign key constraint
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
from sqlalchemy import text


async def fix_foreign_key_cascade():
    """Исправление foreign key для cascade delete"""
    
    print("🔧 Исправление foreign key constraints...")
    
    if not await test_database_connection():
        print("❌ Нет подключения к БД!")
        return False
    
    session_factory = create_async_session_factory()
    
    async with session_factory() as db:
        try:
            # Удаляем старый constraint
            await db.execute(text("""
                ALTER TABLE refresh_tokens 
                DROP CONSTRAINT IF EXISTS refresh_tokens_user_id_fkey
            """))
            
            # Создаем новый constraint с CASCADE
            await db.execute(text("""
                ALTER TABLE refresh_tokens 
                ADD CONSTRAINT refresh_tokens_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            """))
            
            # То же самое для token_blacklist
            await db.execute(text("""
                ALTER TABLE token_blacklist 
                DROP CONSTRAINT IF EXISTS token_blacklist_user_id_fkey
            """))
            
            await db.execute(text("""
                ALTER TABLE token_blacklist 
                ADD CONSTRAINT token_blacklist_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            """))
            
            await db.commit()
            
            print("✅ Foreign key constraints исправлены!")
            return True
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Ошибка при исправлении constraints: {e}")
            return False


if __name__ == "__main__":
    success = asyncio.run(fix_foreign_key_cascade())
    if success:
        print("\n🎉 Готово! Теперь cascade delete должен работать корректно.")
        print("💡 Можете перезапустить тесты.")
    else:
        print("\n❌ Не удалось исправить constraints.")
    
    exit(0 if success else 1)