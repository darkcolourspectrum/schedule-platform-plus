"""
Pydantic-схемы payload-ов событий Admin Service.

Эти схемы описывают контракт событий, публикуемых в RabbitMQ через
outbox-паттерн в exchange 'admin_events'. Потребляются другими сервисами
(Schedule, в перспективе Notification и Analytics).

Изменение схем требует осознанной работы со schema_version:
    - добавление optional-поля = совместимое изменение, schema_version не меняется
    - удаление поля или смена типа = breaking change, schema_version инкрементируется,
      consumer'ы должны быть готовы к обработке нескольких версий

Каждое событие включает технические поля (event_id, event_type, schema_version,
occurred_at) для идемпотентности и эволюции, и доменные поля для бизнес-логики.

Семантика deactivated:
    Удаление студии или кабинета реализовано как soft-delete: запись
    остаётся в БД с is_active=False. Это сохраняет ссылочную целостность
    с lessons и patterns в Schedule Service. Hard-delete не публикуется
    как событие - его не должно быть в проде.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Текущая версия схемы payload-ов. Инкрементируем при breaking-changes.
CURRENT_SCHEMA_VERSION = 1


class _BaseEventPayload(BaseModel):
    """
    Общий базовый класс для всех событий Admin Service.
    
    model_config:
        - frozen=True: payload иммутабелен после создания
        - extra='forbid': запрещаем неожиданные поля
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    # Глобальный UUID события. Совпадает с event_outbox.event_id.
    # Consumer'ы используют его для дедупликации.
    event_id: UUID
    
    # Тип события: 'studio.created', 'classroom.updated' и т.п.
    # Дублируется в outbox.event_type для удобства.
    event_type: str
    
    # Версия схемы payload. При breaking-changes инкрементируется.
    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION)
    
    # Когда событие произошло в бизнес-смысле (не когда было опубликовано).
    # Это время попадания в outbox = время бизнес-операции.
    occurred_at: datetime


# ==================== STUDIO EVENTS ====================


class StudioCreatedPayload(_BaseEventPayload):
    """
    Событие: студия создана.
    
    Consumer (Schedule) должен upsert-нуть запись в studios_cache.
    """
    
    event_type: Literal["studio.created"] = "studio.created"
    
    studio_id: int
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: bool


class StudioUpdatedPayload(_BaseEventPayload):
    """
    Событие: данные студии изменены.
    
    Передаём ПОЛНЫЙ снимок текущего состояния студии, а не diff.
    Consumer перезаписывает локальную копию, опираясь на occurred_at
    для отбрасывания out-of-order устаревших апдейтов.
    """
    
    event_type: Literal["studio.updated"] = "studio.updated"
    
    studio_id: int
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: bool


class StudioDeactivatedPayload(_BaseEventPayload):
    """
    Событие: студия деактивирована (soft-delete).
    
    Consumer должен установить is_active=False у записи в studios_cache.
    Запись НЕ удаляется - она остаётся для ссылочной целостности
    с историческими занятиями.
    """
    
    event_type: Literal["studio.deactivated"] = "studio.deactivated"
    
    studio_id: int


# ==================== CLASSROOM EVENTS ====================


class ClassroomCreatedPayload(_BaseEventPayload):
    """
    Событие: кабинет создан.
    
    Consumer (Schedule) должен upsert-нуть запись в classrooms_cache.
    """
    
    event_type: Literal["classroom.created"] = "classroom.created"
    
    classroom_id: int
    studio_id: int
    name: str
    capacity: int
    description: Optional[str] = None
    equipment: Optional[str] = None
    floor: Optional[int] = None
    room_number: Optional[str] = None
    is_active: bool


class ClassroomUpdatedPayload(_BaseEventPayload):
    """
    Событие: данные кабинета изменены.
    
    Полный снимок текущего состояния, как в studio.updated.
    """
    
    event_type: Literal["classroom.updated"] = "classroom.updated"
    
    classroom_id: int
    studio_id: int
    name: str
    capacity: int
    description: Optional[str] = None
    equipment: Optional[str] = None
    floor: Optional[int] = None
    room_number: Optional[str] = None
    is_active: bool


class ClassroomDeactivatedPayload(_BaseEventPayload):
    """
    Событие: кабинет деактивирован (soft-delete).
    
    Consumer должен установить is_active=False у записи в classrooms_cache.
    """
    
    event_type: Literal["classroom.deactivated"] = "classroom.deactivated"
    
    classroom_id: int


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "StudioCreatedPayload",
    "StudioUpdatedPayload",
    "StudioDeactivatedPayload",
    "ClassroomCreatedPayload",
    "ClassroomUpdatedPayload",
    "ClassroomDeactivatedPayload",
]