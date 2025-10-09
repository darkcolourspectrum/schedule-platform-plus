"""
API Gateway - единая точка входа для всех микросервисов
"""

import logging
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import time

from app.config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="API Gateway",
    description="Единая точка входа для Schedule Platform Plus",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Маппинг сервисов
SERVICES = {
    "auth": settings.auth_service_url,
    "profile": settings.profile_service_url,
    "schedule": settings.schedule_service_url,
}


@app.get("/health")
async def health_check():
    """Health check для Gateway"""
    return {
        "status": "healthy",
        "service": "API Gateway",
        "timestamp": time.time()
    }


@app.api_route(
    "/api/{service_name}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
async def proxy_request(service_name: str, path: str, request: Request):
    """
    Проксирование запросов к микросервисам
    
    Примеры:
    /api/auth/register -> auth-service:8000/api/v1/auth/register
    /api/profile/me -> profile-service:8002/api/v1/profiles/me
    /api/dashboard/stats/system -> profile-service:8002/api/v1/dashboard/stats/system
    """
    
    # Определяем целевой сервис
    if service_name not in SERVICES:
        logger.error(f"Неизвестный сервис: {service_name}")
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    target_service = SERVICES[service_name]
    
    # Формируем URL
    # Специальная обработка для разных сервисов
    if service_name == "dashboard":
        # Dashboard идет через profile service
        target_service = SERVICES["profile"]
        target_url = f"{target_service}/api/v1/dashboard/{path}"
    elif service_name == "studios":
        # Studios идет через auth service
        target_service = SERVICES["auth"]
        target_url = f"{target_service}/api/v1/studios/{path}"
    elif service_name == "auth":
        target_url = f"{target_service}/api/v1/auth/{path}"
    elif service_name == "profile":
        if path.startswith("avatars/"):
            # /api/profile/avatars/1 -> /api/v1/avatars/1
            target_url = f"{target_service}/api/v1/{path}"
        elif path.startswith("dashboard"):
            # /api/profile/dashboard -> /api/v1/dashboard
            target_url = f"{target_service}/api/v1/{path}"
        else:
            # Все остальное через profiles
            target_url = f"{target_service}/api/v1/profiles/{path}"
    elif service_name == "schedule":
        target_url = f"{target_service}/api/v1/schedule/{path}"
    else:
        target_url = f"{target_service}/api/v1/{path}"
    
    # Получаем параметры запроса
    query_params = dict(request.query_params)
    
    # Копируем заголовки (исключаем host)
    headers = dict(request.headers)
    headers.pop("host", None)
    
    # Читаем тело запроса
    body = await request.body()
    
    logger.info(f"Проксирование: {request.method} {target_url}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                params=query_params,
                headers=headers,
                content=body,
            )
            
            # Возвращаем ответ от сервиса
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type")
            )
            
    except httpx.ConnectError as e:
        logger.error(f"Не удалось подключиться к сервису {service_name}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Service {service_name} is unavailable"
        )
    except httpx.TimeoutException as e:
        logger.error(f"Таймаут при обращении к сервису {service_name}: {e}")
        raise HTTPException(
            status_code=504,
            detail=f"Service {service_name} timeout"
        )
    except Exception as e:
        logger.error(f"Ошибка проксирования к {service_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal gateway error"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)