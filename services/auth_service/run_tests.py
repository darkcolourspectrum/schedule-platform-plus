"""
Запуск интеграционных тестов Auth Service
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from tests.test_integration import main


if __name__ == "__main__":
    print("🧪 Интеграционное тестирование Auth Service")
    print("=" * 45)
    print("💡 Убедитесь, что сервер запущен: python run_server.py")
    print("💡 Swagger UI: http://localhost:8000/docs")
    print("-" * 45)
    
    try:
        success = asyncio.run(main())
        if success:
            print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
            print("🎉 Ваш Auth Service работает корректно!")
        else:
            print("\n❌ Некоторые тесты не пройдены")
            exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️  Тестирование прервано пользователем")
        exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        exit(1)