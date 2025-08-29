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