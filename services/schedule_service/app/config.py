from functools import lru_cache
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class Settings(BaseSettings):
    """Конфигурация Schedule Service с использованием Pydantic Settings"""
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    database_host: str = Field("localhost", env="DATABASE_HOST")
    database_port: int = Field(5432, env="DATABASE_PORT")
    database_name: str = Field("schedule_service_db", env="DATABASE_NAME")
    database_user: str = Field(..., env="DATABASE_USER")
    database_password: str = Field(..., env="DATABASE_PASSWORD")
    
    # Redis
    redis_url: str = Field("redis://localhost:6379/1", env="REDIS_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    redis_port: int = Field(6379, env="REDIS_PORT")
    redis_db: int = Field(1, env="REDIS_DB")
    
    # Application
    app_name: str = Field("Schedule Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="ALLOWED_ORIGINS"
    )
    allow_credentials: bool = Field(True, env="ALLOW_CREDENTIALS")
    
    # Auth Service Integration
    auth_service_url: str = Field("http://localhost:8000", env="AUTH_SERVICE_URL")
    auth_service_timeout: int = Field(30, env="AUTH_SERVICE_TIMEOUT")
    
    # Schedule Service Specific
    default_lesson_duration_minutes: int = Field(60, env="DEFAULT_LESSON_DURATION_MINUTES")
    max_weeks_forward: int = Field(4, env="MAX_WEEKS_FORWARD")
    max_weeks_backward: int = Field(1, env="MAX_WEEKS_BACKWARD")
    cache_schedule_ttl: int = Field(300, env="CACHE_SCHEDULE_TTL")  # 5 минут
    
    # Security
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")
    
    @property
    def database_url_sync(self) -> str:
        """Синхронный URL для Alembic"""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")
    
    @property
    def database_url_async(self) -> str:
        """Асинхронный URL для SQLAlchemy"""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://")
        return self.database_url
    
    @property
    def is_production(self) -> bool:
        """Проверка production окружения"""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Проверка development окружения"""
        return self.environment.lower() == "development"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Получение настроек приложения с кэшированием
    Используется lru_cache для оптимизации
    """
    return Settings()


# Глобальный экземпляр настроек
settings = get_settings()