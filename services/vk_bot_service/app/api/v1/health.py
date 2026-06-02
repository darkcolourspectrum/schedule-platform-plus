"""Health-check эндпоинты VK Bot Service."""
from fastapi import APIRouter

from app.config import settings
from app.database.connection import test_database_connection

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    """
    Состояние сервиса для мониторинга и orchestrator'а.

    Возвращает 200 всегда, когда HTTP-часть жива; поля db/vk_configured
    показывают готовность зависимостей. VK может быть не настроен - это
    валидное состояние (сервис работает, входящих сообщений нет).
    """
    db_ok = await test_database_connection()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "db": "ok" if db_ok else "down",
        "vk_configured": settings.vk_configured,
    }
