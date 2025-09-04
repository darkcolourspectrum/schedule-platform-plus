"""
Скрипт запуска сервера Schedule Service
Удобная точка входа для разработки
"""

import asyncio
import sys
import uvicorn
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings


def main():
    """Запуск сервера"""
    
    print(f"🚀 Запуск {settings.app_name} v{settings.app_version}")
    print(f"🔧 Режим: {settings.environment}")
    print(f"🌐 Порт: 8001")
    print(f"📋 Документация: http://localhost:8001/docs")
    print("=" * 50)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,  # Отличный от Auth Service порт
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
        access_log=True,
        reload_dirs=["app"] if settings.debug else None,
    )


if __name__ == "__main__":
    main()