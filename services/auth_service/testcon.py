"""
Минимальный тест psycopg3 без дополнительных параметров
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Исправление для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Прямой URL без конфигурации
DATABASE_URL = "postgresql+psycopg://postgres:kirill1905@localhost:5432/auth_service_db"

async def minimal_test():
    """Минимальный тест подключения"""
    print(f"🔗 Тестируем: {DATABASE_URL}")
    
    try:
        # Создаем движок с минимальными настройками
        engine = create_async_engine(
            DATABASE_URL,
            echo=True
        )
        
        # Тест подключения
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            value = result.scalar()
            
            if value == 1:
                print("✅ Подключение успешно!")
                
                # Информация о базе
                version = await conn.execute(text("SELECT version()"))
                print(f"📊 {version.scalar()}")
                
                await engine.dispose()
                return True
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print(f"📋 Тип: {type(e).__name__}")
        return False

if __name__ == "__main__":
    result = asyncio.run(minimal_test())
    if result:
        print("🎉 Все работает!")
    else:
        print("❌ Не получилось")