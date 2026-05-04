"""
Main FastAPI application
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.router import api_router
from app.database.redis_client import redis_client

from app.messaging.auth_consumer import consumer as auth_consumer
from app.messaging.admin_consumer import consumer as admin_consumer
from app.messaging.publisher_worker import init_worker
from app.database.connection import ScheduleAsyncSessionLocal

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: startup and shutdown"""
    
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    
    await redis_client.connect()
    
    try:
        await auth_consumer.start()
    except Exception as exc:
        logger.error("Failed to start auth event consumer: %s", exc)
        raise
    
    # Запуск consumer'а событий из Admin Service.
    # Слушает studio.* и classroom.* в exchange 'admin_events',
    # синхронизирует локальные studios_cache и classrooms_cache.
    try:
        await admin_consumer.start()
    except Exception as exc:
        logger.error("Failed to start admin event consumer: %s", exc)
        raise
    
    # Запуск outbox-publisher воркера для надёжной публикации событий
    # (lesson.created и т.п.) через транзакционный outbox.
    try:
        outbox_worker = init_worker(ScheduleAsyncSessionLocal)
        await outbox_worker.start()
    except Exception as exc:
        logger.error("Failed to start outbox publisher worker: %s", exc)
        raise

    yield
    
    # Shutdown
    logger.info("Shutting down...")
    
    from app.messaging.publisher_worker import worker as outbox_worker
    if outbox_worker is not None:
        await outbox_worker.stop()
    
    await admin_consumer.stop()
    await auth_consumer.stop()
    await redis_client.disconnect()


# Создаем FastAPI приложение
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Schedule Service для управления расписанием занятий",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
