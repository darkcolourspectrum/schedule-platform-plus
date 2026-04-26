"""Configuration settings for Notification Service"""
from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = Field("Notification Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")
    
    # Server
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8004, env="PORT")
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    
    # Redis (for shared/auth_lib blacklist)
    jwt_blacklist_redis_url: str = Field("redis://localhost:6379/15", env="JWT_BLACKLIST_REDIS_URL")
    
    # JWT
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    
    # CORS
    cors_origins: str = Field("http://localhost:3000,http://localhost:5173", env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    
    # RabbitMQ
    rabbitmq_url: str = Field("amqp://guest:guest@rabbitmq:5672/", env="RABBITMQ_URL")
    
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