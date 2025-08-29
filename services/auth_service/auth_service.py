from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SecurityManager, create_tokens_for_user, TokenPayload
from app.core.exceptions import (
    InvalidCredentialsException,
    UserNotFoundException,
    UserAlreadyExistsException,
    UserInactiveException,
    AccountLockedException,
    InvalidTokenException,
    TokenBlacklistedException,
    PrivacyPolicyNotAcceptedException
)
from app.repositories.user_repository import (
    UserRepository,
    RefreshTokenRepository,
    TokenBlacklistRepository
)
from app.repositories.role_repository import RoleRepository
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.config import settings


class AuthService:
    """Сервис аутентификации и авторизации"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.refresh_token_repo = RefreshTokenRepository(db)
        self.blacklist_repo = TokenBlacklistRepository(db)
        self.role_repo = RoleRepository(db)
        self.security = SecurityManager()
    
    async def register_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        privacy_policy_accepted: bool = False
    ) -> Dict[str, Any]:
        """Регистрация нового пользователя"""
        
        # Проверка согласия на обработку данных
        if not privacy_policy_accepted:
            raise PrivacyPolicyNotAcceptedException()
        
        # Проверка существования пользователя
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            raise UserAlreadyExistsException()
        
        # Получение роли студента по умолчанию
        student_role = await self.role_repo.get_default_student_role()
        if not student_role:
            raise Exception("Default student role not found")
        
        # Создание пользователя
        hashed_password = self.security.hash_password(password)
        user = await self.user_repo.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role_id=student_role.id,
            hashed_password=hashed_password,
            phone=phone,
            privacy_policy_accepted=privacy_policy_accepted
        )
        
        # Создание токенов
        tokens = create_tokens_for_user(
            user_id=user.id,
            email=user.email,
            role=student_role.name,
            studio_id=user.studio_id
        )
        
        # Сохранение refresh токена
        refresh_expires_at = datetime.utcnow() + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        
        await self.refresh_token_repo.create_refresh_token(
            user_id=user.id,
            token=tokens["refresh_token"],
            expires_at=refresh_expires_at
        )
        
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": student_role.name,
                "studio_id": user.studio_id
            },
            "tokens": tokens
        }
    
    async def login_user(
        self,
        email: str,
        password: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Аутентификация пользователя"""