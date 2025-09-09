"""
Общие Pydantic схемы для Profile Service
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    """Базовая схема успешного ответа"""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Базовая схема ответа с ошибкой"""
    success: bool = False
    error: str
    detail: Optional[str] = None
    error_code: Optional[str] = None


class PaginationParams(BaseModel):
    """Параметры пагинации"""
    limit: int = Field(20, ge=1, le=100, description="Количество элементов на странице")
    offset: int = Field(0, ge=0, description="Смещение")


class PaginationInfo(BaseModel):
    """Информация о пагинации"""
    total: int = Field(..., description="Общее количество элементов")
    limit: int = Field(..., description="Количество элементов на странице")
    offset: int = Field(..., description="Смещение")
    has_more: bool = Field(..., description="Есть ли еще элементы")
    page: int = Field(..., description="Номер текущей страницы")
    total_pages: int = Field(..., description="Общее количество страниц")


class PaginatedResponse(BaseModel):
    """Базовая схема пагинированного ответа"""
    items: List[Any] = Field(..., description="Элементы")
    pagination: PaginationInfo = Field(..., description="Информация о пагинации")


class HealthCheckResponse(BaseModel):
    """Схема ответа health check"""
    status: str
    service: str
    version: str
    environment: str
    components: Dict[str, str]
    issues: Optional[List[str]] = None


class ServiceStatsResponse(BaseModel):
    """Схема статистики сервиса"""
    statistics: Dict[str, int]
    settings: Dict[str, Any]


class CacheStatsResponse(BaseModel):
    """Схема статистики кэша"""
    status: str
    redis_url: Optional[str] = None
    default_ttl: int
    profile_ttl: int
    dashboard_ttl: int
    comments_ttl: int
    activity_ttl: int
    error: Optional[str] = None


class ValidationError(BaseModel):
    """Схема ошибки валидации"""
    field: str
    message: str
    value: Optional[Any] = None


class ValidationErrorResponse(BaseModel):
    """Схема ответа с ошибками валидации"""
    success: bool = False
    error: str = "Validation error"
    validation_errors: List[ValidationError]


class SearchParams(BaseModel):
    """Параметры поиска"""
    query: str = Field(..., min_length=1, max_length=100, description="Поисковый запрос")
    limit: int = Field(20, ge=1, le=100, description="Максимальное количество результатов")


class TimeRangeParams(BaseModel):
    """Параметры временного диапазона"""
    start_date: Optional[datetime] = Field(None, description="Начальная дата")
    end_date: Optional[datetime] = Field(None, description="Конечная дата")
    days: Optional[int] = Field(None, ge=1, le=365, description="Количество дней назад")


class FilterParams(BaseModel):
    """Базовые параметры фильтрации"""
    status: Optional[str] = Field(None, description="Статус")
    type: Optional[str] = Field(None, description="Тип")
    user_id: Optional[int] = Field(None, description="ID пользователя")


class BulkOperationRequest(BaseModel):
    """Запрос массовой операции"""
    ids: List[int] = Field(..., min_items=1, max_items=100, description="Список ID")
    action: str = Field(..., description="Действие для выполнения")
    params: Optional[Dict[str, Any]] = Field(None, description="Дополнительные параметры")


class BulkOperationResponse(BaseModel):
    """Ответ массовой операции"""
    success: bool
    processed: int
    failed: int
    errors: List[str] = Field(default_factory=list)
    results: List[Dict[str, Any]] = Field(default_factory=list)


class FileUploadResponse(BaseModel):
    """Ответ загрузки файла"""
    success: bool
    filename: Optional[str] = None
    url: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None


class UserActivitySummary(BaseModel):
    """Сводка активности пользователя"""
    user_id: int
    total_activities: int
    recent_activities: int
    last_activity: Optional[datetime] = None
    most_common_activity: Optional[str] = None


class ServiceInfo(BaseModel):
    """Информация о сервисе"""
    name: str
    version: str
    status: str
    environment: str
    features: Dict[str, bool]
    integrations: Dict[str, str]


class MetricsResponse(BaseModel):
    """Метрики сервиса"""
    requests_total: int
    requests_per_minute: float
    average_response_time: float
    error_rate: float
    cache_hit_rate: float
    active_users: int
    uptime_seconds: int


class ConfigurationResponse(BaseModel):
    """Конфигурация сервиса"""
    max_avatar_size_mb: int
    cache_ttl_profile: int
    cache_ttl_dashboard: int
    cache_ttl_comments: int
    max_comment_length: int
    allowed_image_types: List[str]
    dashboard_data_days_back: int


class BackupInfo(BaseModel):
    """Информация о резервной копии"""
    filename: str
    size_bytes: int
    created_at: datetime
    type: str
    checksum: Optional[str] = None

class SystemMaintenanceInfo(BaseModel):
    """Информация о техническом обслуживании"""
    is_maintenance_mode: bool
    maintenance_start: Optional[datetime] = None
    maintenance_end: Optional[datetime] = None
    message: Optional[str] = None
    affected_services: List[str] = Field(default_factory=list) 