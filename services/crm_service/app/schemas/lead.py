"""
Pydantic-схемы для работы с лидами.

Разделение на схемы запроса и ответа намеренное:
    - схема запроса описывает, что разрешено принять от клиента;
    - схема ответа описывает, что сервис отдаёт наружу.

Публичная ручка (заявка с лендинга) использует максимально строгую
входную схему: данные приходят из неаутентифицированного источника.
"""

import re
from datetime import datetime
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.enums import LeadActivityType, LeadSource, LeadStatus


# Регулярка для нормализованного телефона: опциональный '+' и 7-15 цифр.
# Это базовая проверка "похоже на телефон", а не полная валидация
# международных форматов - она избыточна для MVP.
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")


def _normalize_phone(raw: str) -> str:
    """Убрать пробелы, дефисы и скобки из номера телефона."""
    return re.sub(r"[\s\-()]", "", raw)


# ==================== ЗАПРОСЫ ====================


class LeadPublicCreate(BaseModel):
    """
    Тело публичной заявки с лендинга (POST /api/crm/leads/public).

    source здесь СОЗНАТЕЛЬНО отсутствует: публичная ручка - это вход
    исключительно для лендинга, сервер жёстко проставляет source=landing.
    Если бы source принимался от клиента, заявку можно было бы подделать
    под instagram/referral/manual (последнее вообще означает "заведено
    админом вручную" - семантически невозможно для публичной формы).

    status тоже не принимается: новый лид всегда 'new'.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=200, description="Имя из заявки")
    email: EmailStr = Field(
        ..., description="Email - обязательный контакт, используется при конвертации"
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Телефон - опционально, если человек готов к звонкам",
    )
    studio_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID студии, если на лендинге был выбор филиала",
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        """Нормализовать телефон и проверить формат. None пропускается."""
        if value is None:
            return None
        normalized = _normalize_phone(value)
        if not _PHONE_RE.match(normalized):
            raise ValueError("Invalid phone number format")
        return normalized


class LeadStatusUpdate(BaseModel):
    """
    Тело смены статуса лида (PATCH /api/crm/leads/{id}/status).

    Смена статуса - бизнес-событие: она дописывает запись в журнал
    активностей (а позже будет публиковать событие lead.status_changed).
    Поэтому она вынесена в отдельную ручку и отдельную схему - в отличие
    от обычной правки полей (LeadUpdate).

    Инвариант: лид в статусе 'lost' обязан иметь причину. Это гарантирует
    схема, а не доверие к фронтенду.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    status: LeadStatus = Field(..., description="Новый статус воронки")
    lost_reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Причина проигрыша. Обязательна при status=lost.",
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Необязательный комментарий админа к смене статуса.",
    )

    @model_validator(mode="after")
    def check_lost_reason(self) -> "LeadStatusUpdate":
        """Статус 'lost' требует непустую причину; для прочих она запрещена."""
        if self.status == LeadStatus.LOST:
            if not self.lost_reason or not self.lost_reason.strip():
                raise ValueError("lost_reason is required when status is 'lost'")
        elif self.lost_reason is not None:
            raise ValueError("lost_reason is only allowed when status is 'lost'")
        return self


class LeadUpdate(BaseModel):
    """
    Тело правки полей лида (PATCH /api/crm/leads/{id}).

    Только поля, не являющиеся бизнес-событием: назначение ответственного
    и краткая сводка. Смена статуса сюда НЕ входит - для неё отдельная
    ручка со своей схемой (LeadStatusUpdate).

    Все поля опциональны. Различие "поле не прислали" и "прислали null"
    значимо: assigned_to=null означает снять назначение. Сервисный слой
    разбирает это через model_fields_set - применяются только реально
    присланные поля.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    assigned_to: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID админа-ответственного. null снимает назначение.",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Краткая сводка по лиду.",
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Email лида. Правится, чтобы исправить опечатку до "
        "конвертации (email уходит в User.email и обязан быть валидным).",
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Телефон лида. null снимает телефон.",
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        """Нормализовать телефон. None пропускается (снятие телефона)."""
        if value is None:
            return None
        normalized = _normalize_phone(value)
        if not _PHONE_RE.match(normalized):
            raise ValueError("Invalid phone number format")
        return normalized


class LeadActivityCreate(BaseModel):
    """
    Тело добавления записи в журнал лида (POST /api/crm/leads/{id}/activities).

    Разрешены только типы note и call - это записи, которые админ вносит
    вручную. Тип status_changed создаётся системой автоматически при смене
    статуса и не может быть прислан через API.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: LeadActivityType = Field(
        default=LeadActivityType.NOTE,
        description="Тип записи: note или call.",
    )
    content: str = Field(
        ..., min_length=1, max_length=5000, description="Текст записи."
    )

    @field_validator("type")
    @classmethod
    def forbid_system_type(cls, value: LeadActivityType) -> LeadActivityType:
        """Запретить ручное создание системных записей status_changed."""
        if value == LeadActivityType.STATUS_CHANGED:
            raise ValueError(
                "Activity type 'status_changed' is created by the system "
                "and cannot be submitted manually"
            )
        return value


# ==================== ОТВЕТЫ ====================


class LeadActivityResponse(BaseModel):
    """Запись журнала активностей лида."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    type: LeadActivityType
    content: str
    created_by: Optional[int] = None
    created_at: datetime


class LeadResponse(BaseModel):
    """
    Карточка лида без журнала активностей.

    Используется в ответах списка и публичной ручки. Полная карточка
    с лентой активностей - LeadDetailResponse (добавится позже).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    source: LeadSource
    status: LeadStatus
    studio_id: Optional[int] = None
    assigned_to: Optional[int] = None
    # Имя ответственного админа - обогащается из users_cache в сервисном
    # слое. None, если лид никому не назначен либо назначенный пользователь
    # отсутствует в локальном кеше.
    assigned_to_name: Optional[str] = None
    notes: Optional[str] = None
    lost_reason: Optional[str] = None
    converted_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class LeadDetailResponse(LeadResponse):
    """Полная карточка лида с лентой истории."""

    activities: List[LeadActivityResponse] = Field(default_factory=list)


class LeadListResponse(BaseModel):
    """
    Страница списка лидов.

    total - общее количество лидов, подходящих под фильтры (без учёта
    пагинации); нужно фронту для отрисовки постраничной навигации.
    items - лиды текущей страницы.
    """

    total: int
    items: List[LeadResponse]


class LeadConversionResponse(BaseModel):
    """
    Результат конвертации лида в клиента.

    converted_user_id вынесен наверх отдельным полем (хотя он есть и
    внутри lead) - фронту он нужен сразу после конвертации, чтобы
    открыть форму создания первого занятия для этого пользователя.
    """

    converted_user_id: int
    lead: LeadResponse

class LeadConvertRequest(BaseModel):
    """
    Тело запроса конвертации лида в клиента.

    Все поля опциональны: если поле не передано, оно берётся из лида.
    После применения дефолтов из лида:
        - email обязателен (иначе нельзя создать юзера в Auth);
        - studio_id обязателен (юзер должен быть привязан к филиалу).

    Эти проверки делает сервисный слой (lead_service.convert_to_user),
    а не Pydantic - чтобы выдать осмысленные 400-ошибки.
    """

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    studio_id: Optional[int] = None

class StudioOption(BaseModel):
    """Студия для отображения в select на фронте (модалка конвертации)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
