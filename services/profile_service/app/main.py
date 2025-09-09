"""
FastAPI приложение для Profile Service
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import os

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
    logger.info(f"🚀 Запуск {settings.app_name} v{settings.app_version}")
    logger.info(f"🔧 Режим: {settings.environment}")
    
    # Создаем папку для аватаров если её нет
    avatar_path = settings.avatar_upload_full_path
    if not os.path.exists(avatar_path):
        os.makedirs(avatar_path, exist_ok=True)
        logger.info(f"📁 Создана папка для аватаров: {avatar_path}")
    
    # Тестируем подключение к базе данных
    logger.info("🔄 Проверка подключения к базе данных...")
    db_connected = await test_database_connection()
    
    if not db_connected:
        logger.error("❌ Не удалось подключиться к базе данных!")
        raise RuntimeError("Database connection failed")
    
    # Подключаемся к Redis (опционально)
    try:
        logger.info("🔄 Подключение к Redis...")
        await redis_client.connect()
        redis_connected = await redis_client.test_connection()
        
        if redis_connected:
            logger.info("✅ Redis подключен успешно")
        else:
            logger.warning("⚠️ Redis недоступен, кэширование отключено")
    except Exception as e:
        logger.warning(f"⚠️ Redis недоступен: {e}")
    
    logger.info("✅ Profile Service успешно запущен!")
    
    yield  # Приложение работает
    
    # Shutdown
    logger.info("🔄 Завершение работы приложения...")
    await close_database_connections()
    await redis_client.disconnect()
    logger.info("👋 Profile Service завершен")


# Создание FastAPI приложения
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Микросервис профилей и личных кабинетов для Schedule Platform Plus",
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

# Подключение статических файлов для аватаров
app.mount("/static", StaticFiles(directory="static"), name="static")

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
            "user_profiles": True,
            "dashboard_aggregation": True,
            "comment_system": True,
            "avatar_upload": True,
            "activity_tracking": True,
            "notification_preferences": True,
            "role_based_dashboards": True,
            "data_caching": True,
            "auth_integration": True,
            "schedule_integration": True
        },
        "integrations": {
            "auth_service": settings.auth_service_url,
            "schedule_service": settings.schedule_service_url
        }
    }


@app.get("/health")
async def health_check():
    """Health check для мониторинга"""
    # Проверяем основные компоненты
    health_status = {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "components": {
            "database": "unknown",
            "redis": "unknown",
            "avatar_storage": "unknown"
        }
    }
    
    # Проверка базы данных
    try:
        db_ok = await test_database_connection()
        health_status["components"]["database"] = "healthy" if db_ok else "unhealthy"
    except Exception:
        health_status["components"]["database"] = "unhealthy"
    
    # Проверка Redis
    try:
        redis_ok = await redis_client.test_connection()
        health_status["components"]["redis"] = "healthy" if redis_ok else "unhealthy"
    except Exception:
        health_status["components"]["redis"] = "unhealthy"
    
    # Проверка папки аватаров
    try:
        avatar_path_ok = os.path.exists(settings.avatar_upload_full_path)
        health_status["components"]["avatar_storage"] = "healthy" if avatar_path_ok else "unhealthy"
    except Exception:
        health_status["components"]["avatar_storage"] = "unhealthy"
    
    # Определяем общий статус
    unhealthy_components = [
        comp for comp, status in health_status["components"].items() 
        if status == "unhealthy"
    ]
    
    if unhealthy_components:
        health_status["status"] = "degraded"
        health_status["issues"] = unhealthy_components
    
    return health_status


@app.get("/stats")
async def service_stats():
    """Статистика сервиса (только для разработки)"""
    if not settings.debug:
        return {"error": "Stats endpoint disabled in production"}
    
    try:
        from app.database.connection import AsyncSessionLocal
        from app.models import UserProfile, Comment, UserActivity
        from sqlalchemy import func
        
        async with AsyncSessionLocal() as session:
            # Подсчитываем статистику
            profiles_count = await session.scalar(
                func.count(UserProfile.id)
            )
            comments_count = await session.scalar(
                func.count(Comment.id)
            )
            activities_count = await session.scalar(
                func.count(UserActivity.id)
            )
            
            return {
                "statistics": {
                    "total_profiles": profiles_count or 0,
                    "total_comments": comments_count or 0,
                    "total_activities": activities_count or 0
                },
                "settings": {
                    "max_avatar_size_mb": settings.max_avatar_size_mb,
                    "cache_ttl_profile": settings.cache_user_profile_ttl,
                    "cache_ttl_dashboard": settings.cache_dashboard_ttl,
                    "allowed_image_types": settings.allowed_image_types
                }
            }
    except Exception as e:
        return {"error": f"Failed to get stats: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    
    # Дополнительная настройка для Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,  # Уникальный порт для Profile Service
        reload=settings.debug,
        log_level="info" if settings.debug else "warning"
    )