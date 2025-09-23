"""
Главное приложение Profile Service
"""

import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.router import api_router
from app.database.connection import test_database_connection
from app.services.cache_service import cache_service
from app.services.auth_client import auth_client

# Импортируем middleware из core
from app.core.middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    RequestIDMiddleware,
    ErrorHandlingMiddleware
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Запуск
    logger.info(f"🚀 Запуск {settings.app_name} v{settings.app_version}")
    logger.info(f"🔧 Режим: {settings.environment}")
    
    # Создаем папку для аватаров если её нет
    import os
    avatar_path = getattr(settings, 'avatar_upload_full_path', 'static/avatars')
    if not os.path.exists(avatar_path):
        try:
            os.makedirs(avatar_path, exist_ok=True)
            logger.info(f"📁 Создана папка для аватаров: {avatar_path}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось создать папку аватаров: {e}")
    
    # Тестируем подключение к базе данных
    logger.info("🔄 Проверка подключения к базе данных...")
    try:
        db_connected = await test_database_connection()
        if db_connected:
            logger.info("✅ База данных подключена успешно")
        else:
            logger.warning("⚠️ Проблемы с подключением к базе данных")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
    
    # Проверяем Redis (не критично)
    try:
        logger.info("🔄 Проверка Redis...")
        cache_stats = await cache_service.get_cache_stats()
        if cache_stats.get("enabled", False):
            logger.info("✅ Redis доступен")
        else:
            logger.warning("⚠️ Redis недоступен, кэширование отключено")
    except Exception as e:
        logger.warning(f"⚠️ Redis недоступен: {e}")
    
    # Проверяем Auth Service (не критично)
    try:
        logger.info("🔄 Проверка Auth Service...")
        auth_available = await auth_client.health_check()
        if auth_available:
            logger.info("✅ Auth Service доступен")
        else:
            logger.warning("⚠️ Auth Service недоступен")
    except Exception as e:
        logger.warning(f"⚠️ Auth Service недоступен: {e}")
    
    logger.info("🎉 Profile Service успешно запущен!")
    
    yield
    
    # Завершение
    logger.info("🔄 Завершение работы Profile Service...")
    logger.info("✅ Profile Service остановлен")


# Создание приложения FastAPI
app = FastAPI(
    title="Profile Service",
    description="Микросервис управления профилями пользователей для вокальной школы",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# Добавляем middleware в правильном порядке (последний добавленный выполняется первым)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)

# CORS должен быть последним
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Глобальные обработчики ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Обработчик HTTP исключений"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Обработчик внутренних ошибок сервера"""
    logger.error(f"Внутренняя ошибка сервера: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "Произошла внутренняя ошибка сервера" if not settings.debug else str(exc)
        }
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    """Обработчик ошибок 404"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "detail": "Запрашиваемый ресурс не найден"
        }
    )


# Подключение роутеров
app.include_router(api_router)


# Базовые endpoints
@app.get("/", include_in_schema=False)
async def root():
    """Корневой endpoint"""
    return {
        "service": "Profile Service",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.environment
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Проверка здоровья сервиса"""
    
    components = {
        "database": False,
        "cache": False,
        "auth_service": False
    }
    
    # Проверка базы данных
    try:
        components["database"] = await test_database_connection()
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
        components["database"] = False
    
    # Проверка кэша
    try:
        cache_stats = await cache_service.get_cache_stats()
        components["cache"] = cache_stats.get("enabled", False)
    except Exception as e:
        logger.error(f"Health check cache error: {e}")
        components["cache"] = False
    
    # Проверка Auth Service
    try:
        components["auth_service"] = await auth_client.health_check()
    except Exception as e:
        logger.error(f"Health check auth error: {e}")
        components["auth_service"] = False
    
    # Определяем общий статус (БД критична, остальное - нет)
    is_healthy = components["database"]
    status_code = 200 if is_healthy else 503
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if is_healthy else "unhealthy",
            "service": "Profile Service",
            "version": "1.0.0",
            "environment": settings.environment,
            "components": components,
            "timestamp": time.time()
        }
    )


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Метрики сервиса"""
    try:
        # Базовые метрики
        metrics = {
            "service": "Profile Service",
            "version": "1.0.0",
            "environment": settings.environment,
            "timestamp": time.time()
        }
        
        # Метрики кэша
        try:
            cache_stats = await cache_service.get_cache_stats()
            metrics["cache"] = cache_stats
        except Exception as e:
            metrics["cache"] = {"error": str(e)}
        
        # Метрики базы данных
        try:
            db_healthy = await test_database_connection()
            metrics["database"] = {"healthy": db_healthy}
        except Exception as e:
            metrics["database"] = {"error": str(e)}
        
        return metrics
        
    except Exception as e:
        logger.error(f"Ошибка получения метрик: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get metrics", "detail": str(e)}
        )


@app.get("/info", tags=["Info"])
async def service_info():
    """Информация о сервисе"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "debug": settings.debug,
        "features": {
            "profiles": True,
            "comments": True,
            "dashboard": True,
            "avatars": True,
            "cache": True,
            "auth_integration": True
        }
    }