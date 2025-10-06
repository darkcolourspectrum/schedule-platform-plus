"""
Модульные тесты для app/core/security.py
Тестируем функции безопасности: хэширование паролей и создание JWT токенов
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from jose import jwt

from app.core.security import SecurityManager, create_tokens_for_user, TokenPayload
from app.config import settings


class TestSecurityManager:
    """Тесты для класса SecurityManager"""
    
    def test_hash_password_creates_valid_hash(self):
        """Тест 1: Хэширование пароля создает валидный bcrypt хэш"""
        # Arrange
        password = "testpassword123"
        
        # Act
        hashed = SecurityManager.hash_password(password)
        
        # Assert
        assert hashed is not None
        assert len(hashed) > 0
        assert hashed != password
        assert hashed.startswith("$2b$")
    
    def test_verify_password_with_correct_password_returns_true(self):
        """Тест 2: Проверка правильного пароля возвращает True"""
        # Arrange
        password = "correctpassword"
        hashed = SecurityManager.hash_password(password)
        
        # Act
        result = SecurityManager.verify_password(password, hashed)
        
        # Assert
        assert result is True
    
    def test_verify_password_with_wrong_password_returns_false(self):
        """Тест 3: Проверка неправильного пароля возвращает False"""
        # Arrange
        correct_password = "correctpassword"
        wrong_password = "wrongpassword"
        hashed = SecurityManager.hash_password(correct_password)
        
        # Act
        result = SecurityManager.verify_password(wrong_password, hashed)
        
        # Assert
        assert result is False
    
    def test_verify_password_with_empty_password_returns_false(self):
        """Тест 4: Проверка пустого пароля возвращает False"""
        # Arrange
        hashed = SecurityManager.hash_password("somepassword")
        
        # Act
        result = SecurityManager.verify_password("", hashed)
        
        # Assert
        assert result is False
    
    def test_create_access_token_with_valid_data(self):
        """Тест 5: Создание access токена с валидными данными"""
        # Arrange
        user_data = {
            "user_id": 1,
            "email": "test@example.com",
            "role": "student"
        }
        
        # Act
        token = SecurityManager.create_access_token(user_data)
        
        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token.split('.')) == 3
        
        # Декодируем БЕЗ проверки exp (options={"verify_exp": False})
        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False}
        )
        assert decoded["user_id"] == 1
        assert decoded["email"] == "test@example.com"
        assert decoded["role"] == "student"
        assert decoded["type"] == "access"
        assert "jti" in decoded
        assert "exp" in decoded
        assert "iat" in decoded
    
    def test_create_access_token_with_custom_expiration(self):
        """Тест 6: Создание токена с кастомным временем жизни"""
        # Arrange
        user_data = {"user_id": 1}
        expires_delta = timedelta(hours=2)
        
        # Act
        token = SecurityManager.create_access_token(user_data, expires_delta)
        
        # Assert
        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False}
        )
        
        # Проверяем что exp больше чем сейчас
        current_time = datetime.utcnow().timestamp()
        assert decoded["exp"] > current_time
    
    def test_decode_access_token_with_valid_token(self):
        """Тест 7: Декодирование валидного токена"""
        # Arrange
        user_data = {
            "user_id": 42,
            "email": "user@test.com",
            "role": "teacher"
        }
        token = SecurityManager.create_access_token(user_data)
        
        # Act
        payload = SecurityManager.decode_access_token(token)
        
        # Assert
        assert payload is not None
        assert payload["user_id"] == 42
        assert payload["email"] == "user@test.com"
        assert payload["role"] == "teacher"
        assert payload["type"] == "access"
    
    def test_decode_access_token_with_invalid_token(self):
        """Тест 8: Декодирование невалидного токена возвращает None"""
        # Arrange
        invalid_token = "invalid.jwt.token"
        
        # Act
        payload = SecurityManager.decode_access_token(invalid_token)
        
        # Assert
        assert payload is None
    
    def test_create_refresh_token_returns_uuid(self):
        """Тест 9: Создание refresh токена возвращает UUID строку"""
        # Act
        token = SecurityManager.create_refresh_token()
        
        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) == 36
        assert token.count('-') == 4
    
    def test_validate_token_format_with_valid_jwt(self):
        """Тест 10: Валидация формата правильного JWT токена"""
        # Arrange
        token = SecurityManager.create_access_token({"user_id": 1})
        
        # Act
        is_valid = SecurityManager.validate_token_format(token)
        
        # Assert
        assert is_valid is True
    
    def test_validate_token_format_with_invalid_format(self):
        """Тест 11: Валидация формата неправильного токена"""
        # Arrange
        invalid_tokens = [
            "only-two.parts",
            "one_part",
            ""
        ]
        
        # Act & Assert
        for token in invalid_tokens:
            is_valid = SecurityManager.validate_token_format(token)
            assert is_valid is False, f"Токен '{token}' должен быть невалидным"


class TestCreateTokensForUser:
    """Тесты для функции создания пары токенов"""
    
    def test_create_tokens_for_user_returns_both_tokens(self):
        """Тест 12: Создание токенов возвращает access и refresh токены"""
        # Act
        tokens = create_tokens_for_user(
            user_id=1,
            email="test@example.com",
            role="student"
        )
        
        # Assert
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "token_type" in tokens
        assert tokens["token_type"] == "bearer"
        assert len(tokens["access_token"]) > 0
        assert len(tokens["refresh_token"]) == 36
    
    def test_create_tokens_includes_studio_id_in_payload(self):
        """Тест 13: Токены содержат studio_id если он передан"""
        # Act
        tokens = create_tokens_for_user(
            user_id=5,
            email="teacher@studio.com",
            role="teacher",
            studio_id=10
        )
        
        # Assert
        decoded = jwt.decode(
            tokens["access_token"],
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False}
        )
        assert decoded["studio_id"] == 10


class TestTokenPayload:
    """Тесты для класса TokenPayload"""
    
    def test_token_payload_initialization(self):
        """Тест 14: Инициализация TokenPayload из словаря"""
        # Arrange
        payload_dict = {
            "user_id": 1,
            "email": "user@test.com",
            "role": "student",
            "studio_id": 5,
            "jti": "test-jti",
            "exp": int(datetime.utcnow().timestamp()) + 3600,
            "iat": int(datetime.utcnow().timestamp()),
            "type": "access"
        }
        
        # Act
        token_payload = TokenPayload(payload_dict)
        
        # Assert
        assert token_payload.user_id == 1
        assert token_payload.email == "user@test.com"
        assert token_payload.role == "student"
        assert token_payload.studio_id == 5
        assert token_payload.jti == "test-jti"
    
    def test_token_payload_is_expired_returns_false_for_valid_token(self):
        """Тест 15: is_expired возвращает False для валидного токена"""
        # Arrange
        future_exp = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
        payload_dict = {
            "user_id": 1,
            "email": "test@test.com",
            "exp": future_exp,
            "iat": int(datetime.utcnow().timestamp()),
            "jti": "test",
            "type": "access"
        }
        token_payload = TokenPayload(payload_dict)
        
        # Act
        is_expired = token_payload.is_expired
        
        # Assert
        assert is_expired is False
    
    def test_token_payload_is_expired_returns_true_for_expired_token(self):
        """Тест 16: is_expired возвращает True для истекшего токена"""
        # Arrange
        past_exp = int((datetime.utcnow() - timedelta(hours=1)).timestamp())
        payload_dict = {
            "user_id": 1,
            "email": "test@test.com",
            "exp": past_exp,
            "iat": int(datetime.utcnow().timestamp()),
            "jti": "test",
            "type": "access"
        }
        token_payload = TokenPayload(payload_dict)
        
        # Act
        is_expired = token_payload.is_expired
        
        # Assert
        assert is_expired is True
    
    def test_token_payload_to_dict(self):
        """Тест 17: Конвертация TokenPayload в словарь"""
        # Arrange
        payload_dict = {
            "user_id": 99,
            "email": "convert@test.com",
            "role": "admin",
            "studio_id": None,
            "jti": "unique-id",
            "exp": 1234567890,
            "iat": 1234567800,
            "type": "access"
        }
        token_payload = TokenPayload(payload_dict)
        
        # Act
        result_dict = token_payload.to_dict()
        
        # Assert
        assert result_dict == payload_dict