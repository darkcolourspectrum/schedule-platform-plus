"""
Pydantic-схемы payload-ов событий Auth Service.

Эти схемы описывают контракт событий, который публикуется в RabbitMQ через
outbox-паттерн и потребляется другими сервисами (Schedule, Admin, Notification).

Изменение этих схем требует осознанной работы со schema_version:
    - добавление optional-поля = совместимое изменение, schema_version не меняется
    - удаление поля или смена типа = breaking change, schema_version инкрементируется,
      consumer'ы должны быть готовы к обработке нескольких версий

Каждое событие включает технические поля (event_id, event_type, schema_version,
occurred_at) для идемпотентности и эволюции, и доменные поля для бизнес-логики.
"""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Текущая версия схемы payload-ов. Инкрементируем при breaking-changes.
CURRENT_SCHEMA_VERSION = 1


class _BaseEventPayload(BaseModel):
    """
    Общий базовый класс для всех событий.
    
    Технические поля одинаковы у всех событий, доменные — описаны в наследниках.
    
    model_config:
        - frozen=True: payload иммутабелен после создания
        - extra='forbid': запрещаем неожиданные поля в payload
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    # Глобальный UUID события. Совпадает с event_outbox.event_id.
    # Consumer'ы используют его для дедупликации.
    event_id: UUID
    
    # Тип события: 'user.created', 'user.updated', 'user.deactivated',
    # 'role.changed'. Дублируется в outbox.event_type для удобства.
    event_type: str
    
    # Версия схемы payload. При breaking-changes инкрементируется.
    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION)
    
    # Когда событие произошло в бизнес-смысле (не когда было опубликовано).
    # Это время попадания в outbox = время бизнес-операции.
    occurred_at: datetime


class UserCreatedPayload(_BaseEventPayload):
    """
    Событие: пользователь создан в Auth Service.
    
    Публикуется после успешной регистрации (register_user) или после ручного
    создания пользователя администратором.
    
    Consumer'ы Schedule/Admin должны upsert-нуть запись в users_cache.
    """
    
    event_type: Literal["user.created"] = "user.created"
    
    user_id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    
    role_id: int
    role_name: str  # денормализуем имя роли, чтобы consumer'у не пришлось делать lookup
    
    studio_id: Optional[int] = None
    
    is_active: bool
    is_verified: bool


class UserUpdatedPayload(_BaseEventPayload):
    """
    Событие: данные пользователя изменены.
    
    Публикуется при обновлении профиля (имя, телефон, email), смене studio_id,
    подтверждении email (is_verified -> true) и любых других изменениях.
    
    Содержит ПОЛНЫЙ снимок текущего состояния пользователя, а не diff.
    Это упрощает consumer-логику (просто перезаписать локальную копию)
    и устойчиво к out-of-order доставке: при получении более старого события
    consumer проверяет occurred_at и игнорирует устаревшие апдейты.
    """
    
    event_type: Literal["user.updated"] = "user.updated"
    
    user_id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    
    role_id: int
    role_name: str
    
    studio_id: Optional[int] = None
    
    is_active: bool
    is_verified: bool


class UserDeactivatedPayload(_BaseEventPayload):
    """
    Событие: пользователь деактивирован (мягкое удаление).
    
    Публикуется при is_active -> false, lock account, или явной деактивации
    администратором. Полное удаление аккаунта = отдельное событие user.deleted
    (пока не реализовано, добавим при необходимости GDPR-функционала).
    
    Consumer'ы должны пометить пользователя в локальном кеше как неактивного,
    но НЕ удалять запись (она нужна для отображения исторических данных:
    'занятие, проведённое деактивированным преподавателем').
    """
    
    event_type: Literal["user.deactivated"] = "user.deactivated"
    
    user_id: int
    
    # Опциональная причина (для аудита). 'locked' для автоблокировки после
    # неудачных попыток входа, 'admin_action' для ручной деактивации, etc.
    reason: Optional[str] = None


class RoleChangedPayload(_BaseEventPayload):
    """
    Событие: роль пользователя изменена.
    
    Выделено в отдельный тип события (а не как user.updated), потому что:
        - смена роли = security-relevant событие, должно быть в audit log
        - consumer'ы могут реагировать специфически (инвалидация permissions cache)
        - удобнее для аналитики ('сколько раз меняли роли в этом месяце')
    """
    
    event_type: Literal["role.changed"] = "role.changed"
    
    user_id: int
    
    # Старая роль для аудита.
    old_role_id: int
    old_role_name: str
    
    # Новая роль.
    new_role_id: int
    new_role_name: str
    
    # Кто инициировал смену роли. None для системных операций.
    changed_by_user_id: Optional[int] = None


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "UserCreatedPayload",
    "UserUpdatedPayload",
    "UserDeactivatedPayload",
    "RoleChangedPayload",
]