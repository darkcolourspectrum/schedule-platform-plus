"""
Profile Service Configuration
Настройки для микросервиса профилей с использованием Pydantic Settings
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class Settings(BaseSettings):
    """Конфигурация Profile Service с использованием Pydantic Settings"""
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    database_host: str = Field("localhost", env="DATABASE_HOST")
    database_port: int = Field(5432, env="DATABASE_PORT")
    database_name: str = Field("profile_service_db", env="DATABASE_NAME")
    database_user: str = Field(..., env="DATABASE_USER")
    database_password: str = Field(..., env="DATABASE_PASSWORD")
    
    # Redis
    redis_url: str = Field("redis://localhost:6379/2", env="REDIS_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    redis_port: int = Field(6379, env="REDIS_PORT")
    redis_db: int = Field(2, env="REDIS_DB")  # Отдельная БД для Profile Service
    
    # Application
    app_name: str = Field("Profile Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="ALLOWED_ORIGINS"
    )
    allow_credentials: bool = Field(True, env="ALLOW_CREDENTIALS")
    
    # Microservices Integration
    auth_service_url: str = Field("http://localhost:8000", env="AUTH_SERVICE_URL")
    schedule_service_url: str = Field("http://localhost:8001", env="SCHEDULE_SERVICE_URL")
    auth_service_timeout: int = Field(30, env="AUTH_SERVICE_TIMEOUT")
    schedule_service_timeout: int = Field(30, env="SCHEDULE_SERVICE_TIMEOUT")
    
    # Profile Service Specific Settings
    max_avatar_size_mb: int = Field(5, env="MAX_AVATAR_SIZE_MB")
    allowed_image_types: List[str] = Field(
        default=["image/jpeg", "image/png", "image/webp"],
        env="ALLOWED_IMAGE_TYPES"
    )
    avatar_upload_path: str = Field("static/avatars", env="AVATAR_UPLOAD_PATH")
    
    # Cache TTL settings (в секундах)
    cache_user_profile_ttl: int = Field(600, env="CACHE_USER_PROFILE_TTL")  # 10 минут
    cache_dashboard_ttl: int = Field(300, env="CACHE_DASHBOARD_TTL")  # 5 минут
    cache_comments_ttl: int = Field(180, env="CACHE_COMMENTS_TTL")  # 3 минуты
    cache_activity_ttl: int = Field(3600, env="CACHE_ACTIVITY_TTL")  # 1 час
    
    # Dashboard settings
    max_recent_activities: int = Field(10, env="MAX_RECENT_ACTIVITIES")
    max_upcoming_lessons: int = Field(5, env="MAX_UPCOMING_LESSONS")
    dashboard_data_days_back: int = Field(30, env="DASHBOARD_DATA_DAYS_BACK")
    
    # Comment system settings
    max_comment_length: int = Field(1000, env="MAX_COMMENT_LENGTH")
    allow_comment_editing_hours: int = Field(24, env="ALLOW_COMMENT_EDITING_HOURS")
    
    # Security
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")
    
    @property
    def database_url_sync(self) -> str:
        """Синхронный URL для Alembic миграций"""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    @property
    def database_url_async(self) -> str:
        """Асинхронный URL для SQLAlchemy"""
        if "asyncpg" not in self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        return self.database_url
    
    @property
    def is_development(self) -> bool:
        """Проверка на development окружение"""
        return self.environment.lower() in ["development", "dev", "local"]
    
    @property
    def is_production(self) -> bool:
        """Проверка на production окружение"""
        return self.environment.lower() in ["production", "prod"]
    
    @property
    def avatar_max_size_bytes(self) -> int:
        """Максимальный размер аватара в байтах"""
        return self.max_avatar_size_mb * 1024 * 1024
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Получение настроек с кэшированием"""
    return Settings()


# Глобальный экземпляр настроек
settings = get_settings()