"""
Configuration settings for Admin Service
"""

import os
from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variables"""
    
    # ===== APPLICATION SETTINGS =====
    app_name: str = Field("Admin Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # ===== DATABASE SETTINGS (Admin Service БД) =====
    database_url: str = Field(..., env="DATABASE_URL")
    database_host: str = Field("localhost", env="DATABASE_HOST")
    database_port: int = Field(5432, env="DATABASE_PORT")
    database_name: str = Field("admin_service_db", env="DATABASE_NAME")
    database_user: str = Field("admin_user", env="DATABASE_USER")
    database_password: str = Field(..., env="DATABASE_PASSWORD")
    
    # ===== AUTH SERVICE DATABASE (READ-ONLY) =====
    auth_db_url: str = Field(..., env="AUTH_DB_URL")
    auth_db_host: str = Field("localhost", env="AUTH_DB_HOST")
    auth_db_port: int = Field(5432, env="AUTH_DB_PORT")
    auth_db_name: str = Field("auth_service_db", env="AUTH_DB_NAME")
    auth_db_user: str = Field("auth_user", env="AUTH_DB_USER")
    auth_db_password: str = Field(..., env="AUTH_DB_PASSWORD")
    
    # ===== REDIS SETTINGS =====
    redis_url: str = Field("redis://localhost:6379/3", env="REDIS_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    redis_port: int = Field(6379, env="REDIS_PORT")
    redis_db: int = Field(3, env="REDIS_DB")
    
    # ===== CORS SETTINGS =====
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        env="ALLOWED_ORIGINS"
    )
    allow_credentials: bool = Field(True, env="ALLOW_CREDENTIALS")
    
    # ===== SECURITY =====
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")
    
    # ===== EXTERNAL SERVICES =====
    auth_service_url: str = Field("http://localhost:8000", env="AUTH_SERVICE_URL")
    profile_service_url: str = Field("http://localhost:8002", env="PROFILE_SERVICE_URL")
    schedule_service_url: str = Field("http://localhost:8001", env="SCHEDULE_SERVICE_URL")
    service_timeout: int = Field(30, env="SERVICE_TIMEOUT")
    
    # ===== CACHE TTL SETTINGS (в секундах) =====
    cache_user_ttl: int = Field(300, env="CACHE_USER_TTL")
    cache_studio_ttl: int = Field(600, env="CACHE_STUDIO_TTL")
    cache_classroom_ttl: int = Field(600, env="CACHE_CLASSROOM_TTL")
    cache_stats_ttl: int = Field(60, env="CACHE_STATS_TTL")
    
    # ===== ADMIN DASHBOARD SETTINGS =====
    dashboard_recent_users: int = Field(10, env="DASHBOARD_RECENT_USERS")
    dashboard_recent_activities: int = Field(20, env="DASHBOARD_RECENT_ACTIVITIES")
    dashboard_stats_days_back: int = Field(30, env="DASHBOARD_STATS_DAYS_BACK")
    
    # ===== PAGINATION =====
    default_page_size: int = Field(50, env="DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(100, env="MAX_PAGE_SIZE")
    
    # ===== LOGGING =====
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    @field_validator('allowed_origins', mode='before')
    @classmethod
    def parse_list_from_string(cls, v):
        """Парсинг списка из строки JSON"""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [item.strip() for item in v.split(',')]
        return v
    
    @property
    def database_url_sync(self) -> str:
        """Синхронный URL для Alembic миграций"""
        return self.database_url.replace("+asyncpg", "")
    
    @property
    def database_url_async(self) -> str:
        """Асинхронный URL для SQLAlchemy"""
        if "+asyncpg" not in self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        return self.database_url
    
    @property
    def auth_db_url_async(self) -> str:
        """Асинхронный URL для Auth Service БД"""
        if "+asyncpg" not in self.auth_db_url:
            return self.auth_db_url.replace("postgresql://", "postgresql+asyncpg://")
        return self.auth_db_url
    
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
    """Получение единственного экземпляра настроек с кэшированием"""
    return Settings()


# Глобальный экземпляр настроек
settings = get_settings()
