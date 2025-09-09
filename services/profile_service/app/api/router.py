"""
Главный роутер API для Profile Service
"""

from fastapi import APIRouter

from app.api.v1 import profiles, avatars, dashboard, comments

# Создаем главный роутер API
api_router = APIRouter(prefix="/api/v1")

# Подключаем роутеры модулей
api_router.include_router(profiles.router)
api_router.include_router(avatars.router)
api_router.include_router(dashboard.router)
api_router.include_router(comments.router)

# Дополнительные роутеры можно добавить здесь
# api_router.include_router(activities.router)
# api_router.include_router(notifications.router)