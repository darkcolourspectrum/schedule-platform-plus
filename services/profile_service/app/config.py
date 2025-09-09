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
    redis_db: int = Field(2, env="REDIS_DB")
    
    # Application
    app_name: str = Field("Profile Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://localhost:5173"],
        env="ALLOWED_ORIGINS"
    )
    allow_credentials: bool = Field(True, env="ALLOW_CREDENTIALS")
    
    # Microservices Integration
    auth_service_url: str = Field("http://localhost:8000", env="AUTH_SERVICE_URL")
    schedule_service_url: str = Field("http://localhost:8001", env="SCHEDULE_SERVICE_URL")
    auth_service_timeout: int = Field(30, env="AUTH_SERVICE_TIMEOUT")
    schedule_service_timeout: int = Field(30, env="SCHEDULE_SERVICE_TIMEOUT")
    
    # Profile Service Specific
    max_avatar_size_mb: int = Field(5, env="MAX_AVATAR_SIZE_MB")
    allowed_image_types: List[str] = Field(
        default=["image/jpeg", "image/png", "image/webp"],
        env="ALLOWED_IMAGE_TYPES"
    )
    avatar_upload_path: str = Field("static/avatars", env="AVATAR_UPLOAD_PATH")
    
    # Cache TTL Settings (в секундах)
    cache_user_profile_ttl: int = Field(600, env="CACHE_USER_PROFILE_TTL")  # 10 минут
    cache_dashboard_ttl: int = Field(300, env="CACHE_DASHBOARD_TTL")  # 5 минут
    cache_comments_ttl: int = Field(180, env="CACHE_COMMENTS_TTL")  # 3 минуты
    cache_activity_ttl: int = Field(3600, env="CACHE_ACTIVITY_TTL")  # 1 час
    
    # Dashboard Settings
    max_recent_activities: int = Field(10, env="MAX_RECENT_ACTIVITIES")
    max_upcoming_lessons: int = Field(5, env="MAX_UPCOMING_LESSONS")
    dashboard_data_days_back: int = Field(30, env="DASHBOARD_DATA_DAYS_BACK")
    
    # Comment System Settings
    max_comment_length: int = Field(1000, env="MAX_COMMENT_LENGTH")
    allow_comment_editing_hours: int = Field(24, env="ALLOW_COMMENT_EDITING_HOURS")
    
    # Security
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")
    
    @property
    def database_url_sync(self) -> str:
        """Синхронный URL для Alembic миграций"""
        return self.database_url.replace("+psycopg", "")
    
    @property
    def database_url_async(self) -> str:
        """Асинхронный URL для SQLAlchemy"""
        if "+psycopg" not in self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+psycopg://")
        return self.database_url
    
    @property
    def max_avatar_size_bytes(self) -> int:
        """Максимальный размер аватара в байтах"""
        return self.max_avatar_size_mb * 1024 * 1024
    
    @property
    def avatar_upload_full_path(self) -> str:
        """Полный путь к папке загрузки аватаров"""
        if not os.path.isabs(self.avatar_upload_path):
            return os.path.join(os.getcwd(), self.avatar_upload_path)
        return self.avatar_upload_path


@lru_cache()
def get_settings() -> Settings:
    """Получение единственного экземпляра настроек с кэшированием"""
    return Settings()


# Глобальный экземпляр настроек
settings = get_settings()