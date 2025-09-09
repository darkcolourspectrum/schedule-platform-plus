from functools import lru_cache
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class Settings(BaseSettings):
    """Конфигурация приложения с использованием Pydantic Settings"""
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    database_host: str = Field("localhost", env="DATABASE_HOST")
    database_port: int = Field(5432, env="DATABASE_PORT")
    database_name: str = Field("auth_service_db", env="DATABASE_NAME")
    database_user: str = Field(..., env="DATABASE_USER")
    database_password: str = Field(..., env="DATABASE_PASSWORD")
    
    # Redis
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    redis_port: int = Field(6379, env="REDIS_PORT")
    redis_db: int = Field(0, env="REDIS_DB")
    
    # JWT
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    
    # Application
    app_name: str = Field("Auth Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="ALLOWED_ORIGINS"
    )
    allow_credentials: bool = Field(True, env="ALLOW_CREDENTIALS")
    
    # Email
    smtp_host: str = Field("smtp.gmail.com", env="SMTP_HOST")
    smtp_port: int = Field(587, env="SMTP_PORT")
    smtp_user: Optional[str] = Field(None, env="SMTP_USER")
    smtp_password: Optional[str] = Field(None, env="SMTP_PASSWORD")
    from_email: str = Field("noreply@yourdomain.com", env="FROM_EMAIL")
    
    # Security
    password_min_length: int = Field(8, env="PASSWORD_MIN_LENGTH")
    bcrypt_rounds: int = Field(12, env="BCRYPT_ROUNDS")
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")

    
    # Rate Limiting
    rate_limit_per_minute: int = Field(60, env="RATE_LIMIT_PER_MINUTE")
    
    @property
    def database_url_sync(self) -> str:
        """Синхронный URL для Alembic"""
        return self.database_url.replace("postgresql://", "postgresql://")
    
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