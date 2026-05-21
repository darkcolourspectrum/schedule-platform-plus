"""CRM Service main application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.connection import (
    test_database_connection,
    close_db_connections,
    CrmAsyncSessionLocal,
)
from app.core.exceptions import (
    ConversionError,
    InvalidAssigneeError,
    LeadConflictError,
    LeadNotFoundError,
)
from app.messaging.publisher_worker import init_worker
from app.messaging.auth_consumer import consumer as auth_consumer
from app.messaging.admin_consumer import consumer as admin_consumer
from app.api.v1 import leads

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle сервиса.

    При старте: проверка БД, запуск outbox-publisher воркера.
    Следующий блок добавит сюда запуск RabbitMQ-consumer (auth_events).
    """
    logger.info("Starting %s v%s...", settings.app_name, settings.app_version)
    logger.info("Environment: %s", settings.environment)

    db_ok = await test_database_connection()
    if not db_ok:
        logger.error("Database connection failed!")
    else:
        logger.info("Database connected")

    # Outbox-publisher воркер. Старт обёрнут в try/except: если RabbitMQ
    # недоступен в момент запуска, HTTP-часть сервиса всё равно должна
    # подняться. Неопубликованные события накопятся в outbox и уйдут,
    # когда воркер переподключится.
    outbox_worker = init_worker(CrmAsyncSessionLocal)
    try:
        await outbox_worker.start()
    except Exception as exc:
        logger.error("Failed to start outbox publisher worker: %s", exc)

    # Consumer событий auth_events - наполняет users_cache. Тоже устойчив
    # к недоступности RabbitMQ: connect_robust переподключится сам.
    try:
        await auth_consumer.start()
    except Exception as exc:
        logger.error("Failed to start auth events consumer: %s", exc)

    try:
        await admin_consumer.start()
    except Exception as exc:
        logger.error("Failed to start admin events consumer: %s", exc)

    logger.info("%s started successfully", settings.app_name)
    yield

    logger.info("Shutting down %s...", settings.app_name)
    try:
        await admin_consumer.stop()
    except Exception as exc:
        logger.error("Error stopping admin events consumer: %s", exc)
    try:
        await auth_consumer.stop()
    except Exception as exc:
        logger.error("Error stopping auth events consumer: %s", exc)
    try:
        await outbox_worker.stop()
    except Exception as exc:
        logger.error("Error stopping outbox publisher worker: %s", exc)
    await close_db_connections()
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="CRM-воронка лидов для Schedule Platform Plus",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router, prefix="/api/v1")
app.include_router(leads.studios_router, prefix="/api/v1")


# ==================== EXCEPTION HANDLERS ====================
# Централизованная трансляция доменных исключений в HTTP-ответы.
# Сервисный слой кидает доменные ошибки, не зная про HTTP; маппинг
# "доменная ошибка -> HTTP-код" задаётся здесь один раз.


@app.exception_handler(LeadNotFoundError)
async def lead_not_found_handler(
    request: Request, exc: LeadNotFoundError
) -> JSONResponse:
    """Лид не найден -> 404."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


@app.exception_handler(LeadConflictError)
async def lead_conflict_handler(
    request: Request, exc: LeadConflictError
) -> JSONResponse:
    """Операция несовместима с состоянием лида -> 409."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


@app.exception_handler(InvalidAssigneeError)
async def invalid_assignee_handler(
    request: Request, exc: InvalidAssigneeError
) -> JSONResponse:
    """Невалидное назначение лида (assigned_to) -> 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(ConversionError)
async def conversion_error_handler(
    request: Request, exc: ConversionError
) -> JSONResponse:
    """Конвертация лида невозможна -> 409."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


@app.get("/health")
async def health_check():
    """Health-check endpoint."""
    db_ok = await test_database_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else None,
    }