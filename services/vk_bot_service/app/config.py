"""Configuration settings for VK Bot Service."""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = Field("VK Bot Service", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")

    # Server
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8006, env="PORT")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Redis (for shared/auth_lib blacklist - используется при валидации JWT,
    # если боту понадобится принимать токены; держим для единообразия).
    jwt_blacklist_redis_url: str = Field(
        "redis://localhost:6379/15", env="JWT_BLACKLIST_REDIS_URL"
    )

    # JWT (должен совпадать с Auth Service - бот логинится в платформу
    # внутренними вызовами и валидирует/использует токены при необходимости).
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")

    # Internal API key для межсервисного взаимодействия (bot -> auth/crm/schedule).
    internal_api_key: str = Field(..., env="INTERNAL_API_KEY")

    # ==================== VK GROUP (сообщество, НЕ приложение VK ID) ====================
    # Токен доступа сообщества и его group_id. Получаются в настройках
    # сообщества VK (Управление -> Работа с API -> Ключи доступа и Long Poll API).
    # Это ОТДЕЛЬНАЯ сущность от приложения VK ID, через которое работает
    # авторизация на фронте. Пустые дефолты позволяют сервису подняться
    # без настроенного VK (как auth_service без VK ID).
    vk_group_token: str = Field("", env="VK_GROUP_TOKEN")
    vk_group_id: int = Field(0, env="VK_GROUP_ID")

    # Версия VK API для вызовов messages.send и т.п.
    vk_api_version: str = Field("5.199", env="VK_API_VERSION")

    # Тайм-аут ожидания Long Poll сервера (секунды). VK держит соединение
    # открытым до wait секунд или до появления события.
    vk_longpoll_wait: int = Field(25, env="VK_LONGPOLL_WAIT")

    # ID студии по умолчанию для заявок из бота, если в диалоге студия
    # не выбирается. 0 = не проставлять (заявка уйдёт без studio_id).
    vk_default_studio_id: int = Field(0, env="VK_DEFAULT_STUDIO_ID")

    # ==================== EXTERNAL SERVICES ====================
    auth_service_url: str = Field("http://auth-service:8000", env="AUTH_SERVICE_URL")
    crm_service_url: str = Field("http://crm-service:8005", env="CRM_SERVICE_URL")
    schedule_service_url: str = Field(
        "http://schedule-service:8001", env="SCHEDULE_SERVICE_URL"
    )
    external_service_timeout: float = Field(10.0, env="EXTERNAL_SERVICE_TIMEOUT")

    # ==================== CORS ====================
    cors_origins: str = Field(
        "http://localhost:3000,http://localhost:5173,http://localhost",
        env="CORS_ORIGINS",
    )
    cors_allow_credentials: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")

    # ==================== RabbitMQ ====================
    rabbitmq_url: str = Field("amqp://guest:guest@rabbitmq:5672/", env="RABBITMQ_URL")

    # Outbound retry-воркер: повторная доставка VK-сообщений, которые
    # не удалось отправить с первого раза по транзиентной причине.
    outbound_poll_interval_seconds: float = Field(
        5.0, env="OUTBOUND_POLL_INTERVAL_SECONDS"
    )
    outbound_batch_size: int = Field(50, env="OUTBOUND_BATCH_SIZE")
    outbound_max_attempts: int = Field(5, env="OUTBOUND_MAX_ATTEMPTS")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def database_url_async(self) -> str:
        """URL для async-движка (asyncpg)."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url
        return url.replace("postgresql://", "postgresql+asyncpg://")

    @property
    def database_url_sync(self) -> str:
        """URL для синхронного движка (Alembic)."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def vk_configured(self) -> bool:
        """VK настроен, если есть и токен сообщества, и group_id."""
        return bool(self.vk_group_token) and self.vk_group_id > 0

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
