"""Configuration settings for CRM Service"""
from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = Field("CRM Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")

    # Server
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8005, env="PORT")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Redis (for shared/auth_lib blacklist)
    jwt_blacklist_redis_url: str = Field(
        "redis://localhost:6379/15", env="JWT_BLACKLIST_REDIS_URL"
    )

    # JWT (должен совпадать с Auth Service)
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")

    # Internal API key для межсервисного взаимодействия (CRM -> auth)
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")

    # External services
    auth_service_url: str = Field("http://auth-service:8000", env="AUTH_SERVICE_URL")
    auth_service_timeout: float = Field(10.0, env="AUTH_SERVICE_TIMEOUT")

    # CORS
    cors_origins: str = Field(
        "http://localhost:3000,http://localhost:5173", env="CORS_ORIGINS"
    )
    cors_allow_credentials: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")

    # RabbitMQ (используется с шага 3 - outbox/consumer)
    rabbitmq_url: str = Field("amqp://guest:guest@rabbitmq:5672/", env="RABBITMQ_URL")

    # Outbox publisher worker (используется с шага 3)
    outbox_poll_interval_seconds: float = Field(
        2.0, env="OUTBOX_POLL_INTERVAL_SECONDS"
    )
    outbox_batch_size: int = Field(50, env="OUTBOX_BATCH_SIZE")
    outbox_max_attempts: int = Field(10, env="OUTBOX_MAX_ATTEMPTS")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()