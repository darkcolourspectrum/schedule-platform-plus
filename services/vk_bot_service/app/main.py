"""VK Bot Service - main application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.connection import close_db_connections, test_database_connection
from app.api.v1 import health

from app.messaging.auth_consumer import consumer as auth_consumer
from app.messaging.schedule_consumer import consumer as schedule_consumer
from app.messaging.outbound_worker import worker as outbound_worker
from app.bot.longpoll_worker import worker as longpoll_worker

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Жизненный цикл сервиса.

    Старт воркеров устойчив к недоступности зависимостей: каждый запуск
    в своём try/except, чтобы падение одной зависимости (RabbitMQ/VK) не
    мешало подняться HTTP-части и остальным воркерам.
      - auth_consumer / schedule_consumer: connect_robust сам переподключится;
      - outbound_worker: переживёт временную недоступность VK (записи
        останутся в очереди и уйдут позже);
      - longpoll_worker: не стартует, если VK не настроен (валидно).
    """
    logger.info("Starting %s v%s...", settings.app_name, settings.app_version)
    logger.info("Environment: %s", settings.environment)

    db_ok = await test_database_connection()
    logger.info("Database %s", "connected" if db_ok else "connection FAILED")

    # Consumer событий пользователей (auth_events) - наполняет users_cache.
    try:
        await auth_consumer.start()
    except Exception as exc:
        logger.error("Failed to start auth consumer: %s", exc)

    # Consumer событий расписания (schedule_events) - VK-уведомления.
    try:
        await schedule_consumer.start()
    except Exception as exc:
        logger.error("Failed to start schedule consumer: %s", exc)

    # Воркер повторной отправки исходящих VK-сообщений.
    try:
        await outbound_worker.start()
    except Exception as exc:
        logger.error("Failed to start outbound retry worker: %s", exc)

    # Long Poll воркер приёма входящих сообщений (no-op, если VK не настроен).
    try:
        await longpoll_worker.start()
    except Exception as exc:
        logger.error("Failed to start Long Poll worker: %s", exc)

    logger.info("%s started", settings.app_name)

    yield

    # Graceful shutdown в обратном порядке.
    logger.info("Shutting down %s...", settings.app_name)
    await longpoll_worker.stop()
    await outbound_worker.stop()
    await schedule_consumer.stop()
    await auth_consumer.stop()
    await close_db_connections()
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
# Дублируем health на корне (/health) - так настроены healthcheck'и в
# docker-compose у остальных сервисов проекта.
app.include_router(health.router)
