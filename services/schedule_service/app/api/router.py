from fastapi import APIRouter

from app.api.v1 import schedule, admin

# Главный API роутер
api_router = APIRouter(prefix="/api")

# Версия 1 API
v1_router = APIRouter(prefix="/v1")

# Подключение роутеров
v1_router.include_router(schedule.router)
v1_router.include_router(admin.router)

# Добавление v1 в главный роутер
api_router.include_router(v1_router)