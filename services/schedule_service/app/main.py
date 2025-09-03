"""
FastAPI приложение для Schedule Service
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Исправление для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings
from app.database.connection import test_database_connection, close_database_connections
from app.database.redis_client import redis_client
from app.api.router import api_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager для FastAPI приложения
    """
    # Startup
    logger.info(f"Запуск {settings.app_name} v{settings.app_version}")
    logger.info(f"Режим: {settings.environment}")
    
    # Тестируем подключение к базе данных
    logger.info("Проверка подключения к базе данных...")
    db_connected = await test_database_connection()
    
    if not db_connected:
        logger.error("Не удалось подключиться к базе данных!")
        raise RuntimeError("Database connection failed")
    
    # Подключаемся к Redis (опционально)
    try:
        logger.info("Подключение к Redis...")
        await redis_client.connect()
        redis_connected = await redis_client.test_connection()
        
        if redis_connected:
            logger.info("Redis подключен успешно")
        else:
            logger.warning("Redis недоступен, кеширование отключено")
    except Exception as e:
        logger.warning(f"Redis недоступен: {e}")
    
    logger.info("Schedule Service успешно запущен!")
    
    yield  # Приложение работает
    
    # Shutdown
    logger.info("Завершение работы приложения...")
    await close_database_connections()
    await redis_client.disconnect()
    logger.info("Schedule Service завершен")


# Создание FastAPI приложения
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Микросервис управления расписанием для вокальной школы Schedule Platform Plus",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(api_router)


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "environment": settings.environment,
        "docs": "/docs" if settings.debug else "disabled in production",
        "features": {
            "time_slot_management": True,
            "lesson_scheduling": True,
            "teacher_permissions": True,
            "student_enrollment": True,
            "admin_controls": True,
            "auth_integration": True
        }
    }


@app.get("/health")
async def health_check():
    """Health check для мониторинга"""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "auth_service_url": settings.auth_service_url
    }


if __name__ == "__main__":
    import uvicorn
    
    # Дополнительная настройка для Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,  # Отличный от Auth Service порт
        reload=settings.debug,
        log_level="info" if settings.debug else "warning"
    )