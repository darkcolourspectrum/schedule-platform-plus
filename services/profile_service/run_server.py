#!/usr/bin/env python3
"""
Запуск Profile Service сервера
"""

import asyncio
import sys
import uvicorn

# Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings


def main():
    """Главная функция запуска сервера"""
    
    print(f"🚀 Запуск {settings.app_name} v{settings.app_version}")
    print(f"🔧 Режим: {settings.environment}")
    print(f"🌐 Порт: 8002")
    print(f"📁 Аватары: {settings.avatar_upload_full_path}")
    
    if settings.debug:
        print("📚 Документация: http://localhost:8002/docs")
        print("🔍 Статистика: http://localhost:8002/stats")
    
    print("=" * 50)
    
    # Конфигурация Uvicorn
    uvicorn_config = {
        "app": "app.main:app",
        "host": "0.0.0.0",
        "port": 8002,
        "reload": settings.debug,
        "log_level": "info" if settings.debug else "warning",
        "access_log": settings.debug,
        "use_colors": True,
        "loop": "asyncio"
    }
    
    # Запуск сервера
    uvicorn.run(**uvicorn_config)


if __name__ == "__main__":
    main()