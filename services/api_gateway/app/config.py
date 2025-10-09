"""
Конфигурация API Gateway
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Настройки API Gateway"""
    
    # Основные настройки
    app_name: str = "API Gateway"
    environment: str = "development"
    debug: bool = True
    
    # CORS - строка разделенная запятыми, преобразуется в список
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    
    # URLs микросервисов
    auth_service_url: str = "http://auth-service:8000"
    profile_service_url: str = "http://profile-service:8002"
    schedule_service_url: str = "http://schedule-service:8001"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Преобразует строку CORS origins в список"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()