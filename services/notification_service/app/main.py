"""Notification Service main application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.connection import test_database_connection, close_db_connections
from app.api.v1 import notifications
from app.messaging import consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s...", settings.app_name)
    
    db_ok = await test_database_connection()
    if not db_ok:
        logger.error("Database connection failed!")
    else:
        logger.info("Database connected")
    
    try:
        await consumer.start()
    except Exception as exc:
        logger.error("Failed to start consumer: %s", exc)
    
    logger.info("%s started successfully", settings.app_name)
    yield
    
    logger.info("Shutting down %s...", settings.app_name)
    await consumer.stop()
    await close_db_connections()
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
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

app.include_router(notifications.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    db_ok = await test_database_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
    }