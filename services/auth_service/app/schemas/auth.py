from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import re


class RegisterRequest(BaseModel):
    """Схема для регистрации пользователя"""
    
    email: EmailStr = Field(..., description="Email адрес пользователя")
    password: str = Field(..., min_length=8, max_length=128, description="Пароль")
    first_name: str = Field(..., min_length=1, max_length=100, description="Имя")
    last_name: str = Field(..., min_length=1, max_length=100, description="Фамилия")
    phone: Optional[str] = Field(None, max_length=20, description="Номер телефона")
    privacy_policy_accepted: bool = Field(..., description="Согласие на обработку персональных данных")
    
    @validator('password')
    def validate_password(cls, v):
        """Валидация пароля"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Проверка на наличие хотя бы одной цифры и одной буквы
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        return v
    
    @validator('phone')
    def validate_phone(cls, v):
        """Валидация номера телефона"""
        if v is None:
            return v
        
        # Простая валидация номера телефона
        phone_pattern = r'^\+?[1-9]\d{1,14}$'
        if not re.match(phone_pattern, v.replace(' ', '').replace('-', '')):
            raise ValueError('Invalid phone number format')
        
        return v
    
    @validator('privacy_policy_accepted')
    def validate_privacy_policy(cls, v):
        """Валидация согласия на обработку данных"""
        if not v:
            raise ValueError('Privacy policy must be accepted')
        return v


class LoginRequest(BaseModel):
    """Схема для входа в систему"""
    
    email: EmailStr = Field(..., description="Email адрес пользователя")
    password: str = Field(..., description="Пароль")


class TokenResponse(BaseModel):
    """Схема ответа с токенами"""
    
    access_token: str = Field(..., description="Access токен")
    refresh_token: str = Field(..., description="Refresh токен")
    token_type: str = Field("bearer", description="Тип токена")


class AccessTokenResponse(BaseModel):
    """Схема ответа только с access токеном"""
    
    access_token: str = Field(..., description="Access токен")
    token_type: str = Field("bearer", description="Тип токена")


class UserResponse(BaseModel):
    """Схема ответа с данными пользователя"""
    
    id: int = Field(..., description="ID пользователя")
    email: str = Field(..., description="Email пользователя")
    first_name: str = Field(..., description="Имя пользователя")
    last_name: str = Field(..., description="Фамилия пользователя")
    role: str = Field(..., description="Роль пользователя")
    studio_id: Optional[int] = Field(None, description="ID студии")
    studio_name: Optional[str] = Field(None, description="Название студии")
    is_active: bool = Field(..., description="Активность пользователя")
    is_verified: bool = Field(..., description="Статус верификации")
    
    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Схема полного ответа при аутентификации"""
    
    user: UserResponse = Field(..., description="Данные пользователя")
    tokens: TokenResponse = Field(..., description="Токены")


class RefreshTokenRequest(BaseModel):
    """Схема для обновления токена"""
    
    refresh_token: str = Field(..., description="Refresh токен")


class LogoutRequest(BaseModel):
    """Схема для выхода из системы"""
    
    refresh_token: str = Field(..., description="Refresh токен")


class MessageResponse(BaseModel):
    """Схема стандартного ответа с сообщением"""
    
    message: str = Field(..., description="Сообщение")


class ErrorResponse(BaseModel):
    """Схема ответа с ошибкой"""
    
    detail: str = Field(..., description="Детали ошибки")
    error_code: Optional[str] = Field(None, description="Код ошибки")


class ValidationErrorResponse(BaseModel):
    """Схема ответа с ошибкой валидации"""
    
    detail: str = Field(..., description="Общее описание ошибки")
    errors: Optional[dict] = Field(None, description="Детальные ошибки валидации")


# OAuth схемы
class VKAuthRequest(BaseModel):
    """Схема для OAuth авторизации через VK"""
    
    code: str = Field(..., description="Код авторизации от VK")
    state: Optional[str] = Field(None, description="State параметр")
    privacy_policy_accepted: bool = Field(..., description="Согласие на обработку данных")


class OAuthUserInfo(BaseModel):
    """Схема данных пользователя от OAuth провайдера"""
    
    id: str = Field(..., description="ID пользователя у провайдера")
    email: Optional[str] = Field(None, description="Email пользователя")
    first_name: str = Field(..., description="Имя")
    last_name: str = Field(..., description="Фамилия")
    avatar_url: Optional[str] = Field(None, description="URL аватара")

class VkLoginRequest(BaseModel):
    """
    Тело входа через VK (POST /auth/vk/login).

    Поля приходят с фронта из окна VK ID. Бэкенд сам обменивает их
    на проверенный vk_id (см. vk_id_client) - фронту мы НЕ доверяем
    vk_id напрямую.

    Это схема ИМЕННО входа: ни email, ни согласия на обработку данных
    тут нет (вход - для уже существующего аккаунта). Не путать с
    наброском VKAuthRequest выше - тот под другой, устаревший флоу.
    """

    code: str = Field(..., description="Код авторизации из окна VK ID")
    device_id: str = Field(..., description="device_id из окна VK ID (обязателен для обмена)")
    code_verifier: str = Field(..., description="PKCE code_verifier, парный к code_challenge")
    state: Optional[str] = Field(None, description="Анти-CSRF state, если фронт его слал")

class VkRegisterRequest(BaseModel):
    """
    Тело регистрации через VK (шаг 1) — POST /auth/vk/register.

    code/device_id/code_verifier — из окна VK ID, бэкенд обменивает их
    на проверенный vk_id ОДИН раз (код одноразовый).

    email — ОПЦИОНАЛЕН. Если фронт уже знает email пользователя (например,
    пользователь его ввёл заранее), он его шлёт. Если нет — бэкенд попробует
    взять email из данных VK; а если и там нет — вернёт ответ needs_email,
    и регистрация завершится вторым шагом (vk/register/complete).
    """

    code: str = Field(..., description="Код авторизации из окна VK ID")
    device_id: str = Field(..., description="device_id из окна VK ID")
    code_verifier: str = Field(..., description="PKCE code_verifier")
    state: Optional[str] = Field(None, description="Анти-CSRF state, если фронт его слал")
    email: Optional[EmailStr] = Field(None, description="Email, если уже известен фронту")


class VkRegisterCompleteRequest(BaseModel):
    """
    Тело завершения регистрации через VK (шаг 2) — POST /auth/vk/register/complete.

    Используется, когда на шаге 1 email не был получен. registration_token —
    выданный нами на шаге 1 короткоживущий токен с УЖЕ проверенным vk_id и
    именем/фамилией. Повторный обмен кода не нужен (и невозможен) — vk_id
    берётся из подписанного нами токена.
    """

    registration_token: str = Field(..., description="Токен с шага 1")
    email: EmailStr = Field(..., description="Email, введённый пользователем")


class VkRegisterResponse(BaseModel):
    """
    Ответ шага 1 регистрации.

    Один из двух исходов:
      - completed=True: аккаунт создан, в auth и tokens лежат данные входа
        (как в AuthResponse). needs_email=False.
      - needs_email=True: email не получен, аккаунт НЕ создан. Фронт должен
        показать поле email и вызвать vk/register/complete с registration_token.
        first_name/last_name даны для предзаполнения формы.
    """

    needs_email: bool
    # Заполняется, если аккаунт создан (needs_email=False):
    auth: Optional[AuthResponse] = None
    # Заполняется, если нужен второй шаг (needs_email=True):
    registration_token: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
class VkLinkRequest(BaseModel):
    """
    Тело привязки VK к существующему аккаунту (POST /users/{id}/link-vk).

    Вызывается залогиненным пользователем из своего профиля. code/device_id/
    code_verifier - из окна VK ID; бэкенд обменивает их на проверенный vk_id.
    Email/имя тут НЕ нужны - аккаунт уже существует, меняется только привязка.
    """

    code: str = Field(..., description="Код авторизации из окна VK ID")
    device_id: str = Field(..., description="device_id из окна VK ID")
    code_verifier: str = Field(..., description="PKCE code_verifier")
    state: Optional[str] = Field(None, description="Анти-CSRF state, если фронт его слал")