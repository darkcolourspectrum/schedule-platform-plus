"""
Middleware для Profile Service
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.core.exceptions import RateLimitException
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования запросов"""
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.time()
        
        # Логируем входящий запрос
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        logger.info(
            f"Incoming request: {request.method} {request.url.path} "
            f"from {client_ip} [{user_agent}]"
        )
        
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Логируем результат
        process_time = time.time() - start_time
        logger.info(
            f"Request completed: {request.method} {request.url.path} "
            f"- Status: {response.status_code} "
            f"- Time: {process_time:.3f}s"
        )
        
        # Добавляем заголовки с информацией о времени обработки
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Service"] = "Profile-Service"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware для ограничения скорости запросов"""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # секунд
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        # Пропускаем rate limiting для health check и docs
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        client_ip = request.client.host if request.client else "unknown"
        
        try:
            # Проверяем rate limit
            await self._check_rate_limit(client_ip)
            
            # Обрабатываем запрос
            response = await call_next(request)
            
            return response
            
        except RateLimitException:
            raise
        except Exception as e:
            logger.error(f"Rate limit middleware error: {e}")
            # Если ошибка в middleware - пропускаем запрос
            return await call_next(request)
    
    async def _check_rate_limit(self, client_ip: str):
        """Проверка ограничения скорости запросов"""
        try:
            current_time = int(time.time())
            window_start = current_time - self.window_size
            
            # Ключ для Redis
            rate_limit_key = f"rate_limit:{client_ip}:{window_start // self.window_size}"
            
            # Получаем текущее количество запросов
            current_requests = await cache_service.get(rate_limit_key) or 0
            
            if current_requests >= self.requests_per_minute:
                logger.warning(f"Rate limit exceeded for IP {client_ip}")
                raise RateLimitException()
            
            # Увеличиваем счетчик
            await cache_service.increment(rate_limit_key)
            
            # Устанавливаем TTL для ключа
            if current_requests == 0:
                await cache_service.set(rate_limit_key, 1, ttl=self.window_size)
            
        except RateLimitException:
            raise
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Если Redis недоступен - пропускаем rate limiting


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware для добавления заголовков безопасности"""
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        
        # Добавляем заголовки безопасности
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "img-src 'self' data: https:; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'"
            )
        }
        
        for header_name, header_value in security_headers.items():
            response.headers[header_name] = header_value
        
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware для добавления уникального ID запроса"""
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        import uuid
        
        # Генерируем уникальный ID для запроса
        request_id = str(uuid.uuid4())
        
        # Добавляем в контекст запроса
        request.state.request_id = request_id
        
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Добавляем ID в заголовки ответа
        response.headers["X-Request-ID"] = request_id
        
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware для обработки ошибок"""
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            # Логируем неожиданные ошибки
            request_id = getattr(request.state, "request_id", "unknown")
            logger.error(
                f"Unhandled error in request {request_id}: {e}",
                exc_info=True
            )
            
            # Повторно выбрасываем исключение для обработки FastAPI
            raise