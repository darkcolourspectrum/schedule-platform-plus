"""
Configuration settings for Schedule Service
"""

import os
from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variables"""
    
    # ===== APPLICATION SETTINGS =====
    app_name: str = Field("Schedule Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # ===== SERVER SETTINGS =====
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8083, env="PORT")
    
    # ===== DATABASE SETTINGS (Schedule Service БД) =====
    database_url: str = Field(..., env="DATABASE_URL")
    database_host: str = Field("localhost", env="DATABASE_HOST")
    database_port: int = Field(5432, env="DATABASE_PORT")
    database_name: str = Field("schedule_service_db", env="DATABASE_NAME")
    database_user: str = Field("schedule_user", env="DATABASE_USER")
    database_password: str = Field(..., env="DATABASE_PASSWORD")
    
    # ===== AUTH SERVICE DATABASE (READ-ONLY) =====
    auth_db_url: str = Field(..., env="AUTH_DB_URL")
    auth_db_host: str = Field("localhost", env="AUTH_DB_HOST")
    auth_db_port: int = Field(5432, env="AUTH_DB_PORT")
    auth_db_name: str = Field("auth_service_db", env="AUTH_DB_NAME")
    auth_db_user: str = Field("auth_user", env="AUTH_DB_USER")
    auth_db_password: str = Field(..., env="AUTH_DB_PASSWORD")
    
    # ===== REDIS SETTINGS =====
    redis_url: str = Field("redis://localhost:6379/4", env="REDIS_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    redis_port: int = Field(6379, env="REDIS_PORT")
    redis_db: int = Field(4, env="REDIS_DB")
    redis_cache_ttl: int = Field(3600, env="REDIS_CACHE_TTL")
    
    # ===== JWT SETTINGS =====
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # ===== CORS SETTINGS =====
    cors_origins: str = Field("http://localhost:3000,http://localhost:5173", env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    
    # ===== INTERNAL API KEY =====
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")
    
    # ===== ADMIN SERVICE SETTINGS =====
    admin_service_url: str = Field("http://localhost:8082", env="ADMIN_SERVICE_URL")
    admin_service_timeout: int = Field(10, env="ADMIN_SERVICE_TIMEOUT")
    
    # ===== SCHEDULE SETTINGS =====
    schedule_generation_weeks: int = Field(2, env="SCHEDULE_GENERATION_WEEKS")
    default_lesson_duration_minutes: int = Field(60, env="DEFAULT_LESSON_DURATION_MINUTES")
    schedule_timezone: str = Field("Asia/Tomsk", env="SCHEDULE_TIMEZONE")
    working_hours_start: str = Field("09:00", env="WORKING_HOURS_START")
    working_hours_end: str = Field("20:00", env="WORKING_HOURS_END")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string to list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def database_url_async(self) -> str:
        """Async database URL for Schedule Service"""
        return self.database_url
    
    @property
    def database_url_sync(self) -> str:
        """Sync database URL for migrations"""
        return self.database_url.replace("+asyncpg", "")
    
    @property
    def auth_db_url_async(self) -> str:
        """Async database URL for Auth Service (READ-ONLY)"""
        return self.auth_db_url
    
    @property
    def auth_db_url_sync(self) -> str:
        """Sync database URL for Auth Service"""
        return self.auth_db_url.replace("+asyncpg", "")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
