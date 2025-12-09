"""
Admin Service - Main Application
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.connection import (
    test_admin_db_connection,
    test_auth_db_connection,
    close_db_connections
)
from app.database.redis_client import redis_client
from app.api.v1 import studios, classrooms, users, user_management, dashboard

# Logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events"""
    # Startup
    logger.info(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    
    # Connect to Redis
    await redis_client.connect()
    
    # Test database connections
    admin_db_ok = await test_admin_db_connection()
    auth_db_ok = await test_auth_db_connection()
    
    if not admin_db_ok:
        logger.error("❌ Admin DB connection failed!")
    else:
        logger.info("✅ Admin DB connected")
    
    if not auth_db_ok:
        logger.error("❌ Auth DB connection failed!")
    else:
        logger.info("✅ Auth DB (READ-ONLY) connected")
    
    logger.info(f"✅ {settings.app_name} started successfully")
    
    yield
    
    # Shutdown
    logger.info("🔄 Shutting down Admin Service...")
    await redis_client.disconnect()
    await close_db_connections()
    logger.info("✅ Admin Service stopped")

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Administrative panel and CRM for Schedule Platform Plus",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(studios.router, prefix="/api/v1")
app.include_router(classrooms.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")

app.include_router(user_management.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    admin_db_ok = await test_admin_db_connection()
    auth_db_ok = await test_auth_db_connection()
    redis_ok = redis_client.is_connected
    
    return {
        "status": "healthy" if (admin_db_ok and auth_db_ok) else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "databases": {
            "admin_db": "connected" if admin_db_ok else "disconnected",
            "auth_db_readonly": "connected" if auth_db_ok else "disconnected"
        },
        "redis": "connected" if redis_ok else "disconnected"
    }

@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else None
    }
