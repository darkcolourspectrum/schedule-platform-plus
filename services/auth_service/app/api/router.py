from fastapi import APIRouter

from app.api.v1 import auth, users, roles, admin, studios

# Главный API роутер
api_router = APIRouter(prefix="/api")

# Версия 1 API
v1_router = APIRouter(prefix="/v1")

# Подключение роутеров
v1_router.include_router(auth.router)
v1_router.include_router(users.router)
v1_router.include_router(roles.router)
v1_router.include_router(admin.router)
v1_router.include_router(studios.router)

# Добавление v1 в главный роутер
api_router.include_router(v1_router)