"""
Health check endpoints
"""

from fastapi import APIRouter

from app.schemas.common import HealthCheckResponse
from app.database.connection import (
    check_database_connection,
    check_auth_database_connection
)
from app.database.redis_client import redis_client
from app.config import settings

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check"
)
async def health_check():
    """Проверка состояния сервиса"""
    
    # Проверяем подключения
    db_status = await check_database_connection()
    auth_db_status = await check_auth_database_connection()
    redis_status = await redis_client.exists("health_check")
    
    return HealthCheckResponse(
        status="healthy" if all([db_status, auth_db_status]) else "unhealthy",
        service=settings.app_name,
        version=settings.app_version,
        database=db_status,
        auth_database=auth_db_status,
        redis=redis_status
    )
