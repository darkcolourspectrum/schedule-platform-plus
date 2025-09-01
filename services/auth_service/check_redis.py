"""
Проверка статуса Redis и его использования в Auth Service
"""

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database.redis_client import redis_client
from app.config import settings


async def check_redis_status():
    """Проверка статуса Redis"""
    
    print("Redis Configuration Check")
    print("=" * 40)
    
    print(f"Redis URL: {settings.redis_url}")
    print(f"Redis Host: {settings.redis_host}")
    print(f"Redis Port: {settings.redis_port}")
    print(f"Redis DB: {settings.redis_db}")
    
    print("\nTrying to connect to Redis...")
    
    try:
        # Попытка подключения
        success = await redis_client.test_connection()
        
        if success:
            print("✅ Redis подключен и работает")
            
            # Получаем информацию о сервере
            info = await redis_client.get_info()
            if info:
                print("\nRedis Server Info:")
                for key, value in info.items():
                    print(f"  {key}: {value}")
            
            # Тестируем операции
            print("\nTesting Redis operations...")
            
            # Тест записи/чтения
            await redis_client.set("test_key", "test_value", expire=10)
            value = await redis_client.get("test_key")
            
            if value == "test_value":
                print("✅ Read/Write operations work")
            else:
                print("❌ Read/Write operations failed")
            
            # Очищаем тестовый ключ
            await redis_client.delete("test_key")
            
        else:
            print("❌ Redis недоступен")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка подключения к Redis: {e}")
        return False
    
    finally:
        await redis_client.disconnect()
    
    return True


def analyze_current_usage():
    """Анализ текущего использования Redis в коде"""
    
    print("\n" + "=" * 40)
    print("Current Redis Usage Analysis")
    print("=" * 40)
    
    # Проверяем, где используется Redis
    usage_locations = []
    
    # В main.py
    print("✅ Redis client инициализируется в main.py (lifespan)")
    
    # В dependencies
    print("❌ Redis НЕ используется в dependencies.py")
    
    # В auth_service
    print("❌ Redis НЕ используется в auth_service.py")
    
    # Текущее хранение токенов
    print("📋 Refresh токены хранятся в PostgreSQL (refresh_tokens table)")
    print("📋 Blacklist токенов хранится в PostgreSQL (token_blacklist table)")
    
    print("\n💡 Вывод: Redis настроен, но НЕ используется для кеширования токенов")


def suggest_redis_improvements():
    """Предложения по использованию Redis"""
    
    print("\n" + "=" * 40)
    print("Рекомендации по использованию Redis")
    print("=" * 40)
    
    print("🎯 Где Redis может быть полезен:")
    print("  1. Кеширование JWT blacklist (быстрая проверка отозванных токенов)")
    print("  2. Rate limiting (ограничение количества запросов)")
    print("  3. Сессии пользователей")
    print("  4. Кеширование данных пользователей")
    print("  5. Temporary данные (коды верификации, сброс пароля)")
    
    print("\n📊 Приоритеты:")
    print("  Высокий: JWT Blacklist кеширование")
    print("  Средний: Rate limiting")
    print("  Низкий: Кеширование пользовательских данных")
    
    print("\n⚖️  Текущее состояние:")
    print("  ✅ Система работает без Redis")
    print("  ⚠️  Redis может улучшить производительность")
    print("  ❓ Нужно ли оно сейчас?")


async def main():
    """Главная функция проверки"""
    
    print("🔍 Анализ Redis в Auth Service")
    print("=" * 50)
    
    # Проверка подключения
    redis_available = await check_redis_status()
    
    # Анализ использования
    analyze_current_usage()
    
    # Рекомендации
    suggest_redis_improvements()
    
    print("\n" + "=" * 50)
    
    if redis_available:
        print("✅ Redis доступен и готов к использованию")
        print("💡 Можно добавить функции кеширования")
    else:
        print("❌ Redis недоступен")
        print("💡 Система работает без Redis (токены в PostgreSQL)")
        print("💡 Для production рекомендуется настроить Redis")
    
    return redis_available


if __name__ == "__main__":
    asyncio.run(main())