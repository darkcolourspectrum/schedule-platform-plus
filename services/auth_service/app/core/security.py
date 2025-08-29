from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt

from app.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SecurityManager:
    """Менеджер безопасности для JWT и паролей"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Хэширование пароля"""
        return pwd_context.hash(password, rounds=settings.bcrypt_rounds)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Проверка пароля"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Создание access токена"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.jwt_access_token_expire_minutes
            )
        
        # Добавляем стандартные claims
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),  # Уникальный ID токена для blacklist
            "type": "access"
        })
        
        return jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
    
    @staticmethod
    def create_refresh_token() -> str:
        """Создание refresh токена (случайная строка)"""
        return str(uuid.uuid4())
    
    @staticmethod
    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        """Декодирование access токена"""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            
            # Проверяем тип токена
            if payload.get("type") != "access":
                return None
                
            return payload
        except JWTError:
            return None
    
    @staticmethod
    def get_token_jti(token: str) -> Optional[str]:
        """Получение JTI из токена без полной валидации"""
        try:
            # Декодируем без проверки подписи для получения JTI
            payload = jwt.decode(
                token,
                options={"verify_signature": False}
            )
            return payload.get("jti")
        except JWTError:
            return None
    
    @staticmethod
    def validate_token_format(token: str) -> bool:
        """Базовая проверка формата JWT токена"""
        try:
            parts = token.split('.')
            return len(parts) == 3
        except:
            return False


class TokenPayload:
    """Структура payload токена"""
    
    def __init__(self, payload: Dict[str, Any]):
        self.user_id: int = payload.get("user_id")
        self.email: str = payload.get("email")
        self.role: str = payload.get("role")
        self.studio_id: Optional[int] = payload.get("studio_id")
        self.jti: str = payload.get("jti")
        self.exp: int = payload.get("exp")
        self.iat: int = payload.get("iat")
        self.type: str = payload.get("type")
    
    @property
    def is_expired(self) -> bool:
        """Проверка истечения токена"""
        return datetime.utcnow().timestamp() >= self.exp
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "studio_id": self.studio_id,
            "jti": self.jti,
            "exp": self.exp,
            "iat": self.iat,
            "type": self.type
        }


def create_tokens_for_user(
    user_id: int,
    email: str,
    role: str,
    studio_id: Optional[int] = None
) -> Dict[str, str]:
    """Создание пары токенов для пользователя"""
    
    # Payload для access токена
    access_payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "studio_id": studio_id
    }
    
    # Создаем токены
    access_token = SecurityManager.create_access_token(access_payload)
    refresh_token = SecurityManager.create_refresh_token()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }