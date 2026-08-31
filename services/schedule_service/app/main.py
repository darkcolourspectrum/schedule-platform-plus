"""
Main FastAPI application
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from fastapi.middleware.cors import CORSMiddleware

from app.core.db_errors import translate_integrity_error
from app.core.exceptions import (
    ClassroomConflictException,
    DuplicateLessonException,
    GenerationException,
    InvalidLessonStatusException,
    InvalidTimeRangeException,
    LessonNotFoundException,
    PermissionDeniedException,
    RecurringPatternNotFoundException,
    ScheduleServiceException,
    StudentConflictException,
    TeacherConflictException,
    LessonImmutableException,
)
from app.domain.recurrence import RecurrenceError

from app.config import settings
from app.api.v1.router import api_router
from app.database.redis_client import redis_client

from app.messaging.auth_consumer import consumer as auth_consumer
from app.messaging.admin_consumer import consumer as admin_consumer
from app.messaging.publisher_worker import init_worker
from app.database.connection import ScheduleAsyncSessionLocal

from app.services.generation_worker import init_generation_worker

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

    # Фоновое продление горизонта расписания.
    # Заменяет прежний вызов из GET-запроса расписания студии: просмотр
    # расписания больше не является операцией записи.
    if settings.schedule_generation_enabled:
        try:
            generation_worker = init_generation_worker(ScheduleAsyncSessionLocal)
            await generation_worker.start()
        except Exception as exc:
            # В отличие от outbox, генерация не критична для старта:
            # занятия создаются и при сохранении шаблона, воркер лишь
            # продлевает горизонт. Сервис должен подняться в любом случае.
            logger.error("Failed to start generation worker: %s", exc)
    else:
        logger.info("Schedule generation worker disabled by settings")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")

    from app.services.generation_worker import worker as generation_worker
    if generation_worker is not None:
        await generation_worker.stop()
    
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

# ==================== EXCEPTION HANDLERS ====================
# Сервисный слой кидает доменные ошибки, ничего не зная про HTTP.
# Соответствие "доменная ошибка -> код ответа" задаётся здесь один раз.
# До этого блока любая доменная ошибка превращалась в 500 с пустым телом.

_NOT_FOUND = (RecurringPatternNotFoundException, LessonNotFoundException)
_CONFLICT = (
    ClassroomConflictException,
    TeacherConflictException,
    StudentConflictException,
    DuplicateLessonException,
)


@app.exception_handler(RecurringPatternNotFoundException)
@app.exception_handler(LessonNotFoundException)
async def not_found_handler(request: Request, exc: ScheduleServiceException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.message},
    )


@app.exception_handler(ClassroomConflictException)
@app.exception_handler(TeacherConflictException)
@app.exception_handler(StudentConflictException)
@app.exception_handler(DuplicateLessonException)
async def conflict_handler(request: Request, exc: ScheduleServiceException):
    """Занятое время или дубль -> 409."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": exc.message, "reason": exc.details},
    )


@app.exception_handler(PermissionDeniedException)
async def permission_denied_handler(
    request: Request, exc: PermissionDeniedException
):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": exc.message},
    )


@app.exception_handler(RecurrenceError)
async def recurrence_error_handler(request: Request, exc: RecurrenceError):
    """Ошибка расчёта повторений (полночь, день недели, периодичность) -> 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """
    Нарушение констрейнта БД.

    Штатно сюда не попадаем: сервис спрашивает ConflictService заранее.
    Сюда приходят гонки двух параллельных запросов и расхождения между
    проверкой и констрейнтом. Распознанные переводим в 409/400,
    нераспознанные оставляем 500 - это баг, и он должен быть шумным.
    """
    domain_exc = translate_integrity_error(exc)

    if domain_exc is None:
        logger.exception("Unhandled integrity error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Внутренняя ошибка при сохранении данных"},
        )

    code = (
        status.HTTP_409_CONFLICT
        if isinstance(domain_exc, _CONFLICT)
        else status.HTTP_400_BAD_REQUEST
    )
    return JSONResponse(
        status_code=code,
        content={"detail": domain_exc.message},
    )


@app.exception_handler(ScheduleServiceException)
async def schedule_exception_handler(
    request: Request, exc: ScheduleServiceException
):
    """Остальные доменные ошибки -> 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )

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
