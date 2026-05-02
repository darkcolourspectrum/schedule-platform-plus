from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.security import SecurityManager, create_tokens_for_user, TokenPayload
from app.core.exceptions import (
    InvalidCredentialsException,
    UserNotFoundException,
    UserAlreadyExistsException,
    UserInactiveException,
    AccountLockedException,
    InvalidTokenException,
    TokenBlacklistedException,
    PrivacyPolicyNotAcceptedException,
    RateLimitExceededException
)
from app.repositories.user_repository import (
    UserRepository,
    RefreshTokenRepository,
    TokenBlacklistRepository
)
from app.repositories.role_repository import RoleRepository
from app.services.redis_blacklist_service import RedisBlacklistService
from app.services.redis_rate_limiter import AuthRateLimiter
from app.messaging.outbox import (
    record_user_created,
    record_user_deactivated,
)
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Сервис аутентификации и авторизации"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.refresh_token_repo = RefreshTokenRepository(db)
        self.blacklist_repo = TokenBlacklistRepository(db)
        self.role_repo = RoleRepository(db)
        self.security = SecurityManager()
        
        # Redis сервисы для производительности
        self.redis_blacklist = RedisBlacklistService(db)
        self.rate_limiter = AuthRateLimiter()
    
    async def register_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        privacy_policy_accepted: bool = False,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Регистрация нового пользователя с rate limiting"""
        
        # Rate limiting для регистрации
        if ip_address:
            try:
                await self.rate_limiter.check_register_rate_limit(ip_address)
            except RateLimitExceededException as e:
                logger.warning(f"Registration rate limit exceeded for IP {ip_address}")
                raise e
        
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
        
        try:
            # Создание пользователя (flush -> id есть, но без commit)
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
            
            # Сохранение refresh токена (без commit)
            refresh_expires_at = datetime.utcnow() + timedelta(
                days=settings.jwt_refresh_token_expire_days
            )
            await self.refresh_token_repo.create_refresh_token(
                user_id=user.id,
                token=tokens["refresh_token"],
                expires_at=refresh_expires_at
            )
            
            # Запись события в outbox в той же транзакции
            await record_user_created(self.db, user, role_name=student_role.name)
            
            # Атомарный commit: пользователь + refresh-токен + outbox-событие
            await self.db.commit()
            
        except Exception:
            await self.db.rollback()
            raise
        
        logger.info(f"User registered: {email} from IP {ip_address}")
        
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": student_role.name,
                "studio_id": user.studio_id,
                "studio_name": None,
                "is_active": user.is_active,
                "is_verified": user.is_verified
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
        
        # Получение пользователя
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise InvalidCredentialsException()
        
        # Проверка блокировки аккаунта
        if user.is_locked:
            locked_until = user.locked_until.isoformat() if user.locked_until else None
            raise AccountLockedException(locked_until=locked_until)
        
        # Проверка активности пользователя
        if not user.is_active:
            raise UserInactiveException()
        
        # Проверка пароля
        if not self.security.verify_password(password, user.hashed_password):
            try:
                # Увеличиваем счетчик неудачных попыток
                await self.user_repo.increment_login_attempts(user.id)
                
                # После 5 попыток блокируем аккаунт + публикуем событие деактивации
                if user.login_attempts + 1 >= 5:
                    await self.user_repo.lock_user_account(user.id, lock_duration_minutes=30)
                    await record_user_deactivated(
                        self.db,
                        user_id=user.id,
                        reason="locked_too_many_failed_logins"
                    )
                
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise
            
            raise InvalidCredentialsException()
        
        try:
            # Сброс счетчика попыток при успешном входе
            await self.user_repo.reset_login_attempts(user.id)
            await self.user_repo.update_last_login(user.id)
            
            # Создание токенов
            tokens = create_tokens_for_user(
                user_id=user.id,
                email=user.email,
                role=user.role.name,
                studio_id=user.studio_id
            )
            
            # Сохранение refresh токена
            refresh_expires_at = datetime.utcnow() + timedelta(
                days=settings.jwt_refresh_token_expire_days
            )
            await self.refresh_token_repo.create_refresh_token(
                user_id=user.id,
                token=tokens["refresh_token"],
                expires_at=refresh_expires_at,
                device_info=device_info,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role.name,
                "studio_id": user.studio_id,
                "studio_name": None,
                "is_active": user.is_active,
                "is_verified": user.is_verified
            },
            "tokens": tokens
        }
    
    async def refresh_access_token(self, refresh_token: str, user_id: Optional[int] = None) -> Dict[str, str]:
        """Обновление access токена по refresh токену с rate limiting"""
        
        # Rate limiting для обновления токенов
        if user_id:
            try:
                await self.rate_limiter.check_refresh_rate_limit(user_id)
            except RateLimitExceededException as e:
                logger.warning(f"Refresh token rate limit exceeded for user {user_id}")
                raise e
        
        # Получение refresh токена из БД
        token_record = await self.refresh_token_repo.get_by_token(refresh_token)
        if not token_record:
            raise InvalidTokenException()
        
        # Проверка валидности токена
        if not token_record.is_valid:
            raise InvalidTokenException()
        
        # Получение пользователя
        user = token_record.user
        if not user.is_active:
            raise UserInactiveException()
        
        # Создание нового access токена (read-only операция, commit не нужен)
        tokens = create_tokens_for_user(
            user_id=user.id,
            email=user.email,
            role=user.role.name,
            studio_id=user.studio_id
        )
        
        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer"
        }
    
    async def logout_user(
        self,
        refresh_token: str,
        access_token: Optional[str] = None
    ) -> Dict[str, str]:
        """Выход пользователя из системы с Redis blacklist"""
        
        try:
            # Отзыв refresh токена
            await self.refresh_token_repo.revoke_token(refresh_token)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        
        # Добавление access токена в blacklist через Redis (отдельная подсистема)
        if access_token:
            token_jti = self.security.get_token_jti(access_token)
            if token_jti:
                token_payload = self.security.decode_access_token(access_token)
                if token_payload:
                    expires_at = datetime.utcfromtimestamp(token_payload["exp"])
                    
                    await self.redis_blacklist.add_token_to_blacklist(
                        token_jti=token_jti,
                        token_type="access",
                        expires_at=expires_at,
                        user_id=token_payload.get("user_id"),
                        reason="logout"
                    )
                    
                    logger.info(f"Access token added to blacklist: {token_jti[:8]}...")
        
        return {"message": "Successfully logged out"}
    
    async def logout_all_devices(self, user_id: int) -> Dict[str, str]:
        """Выход пользователя со всех устройств с очисткой кеша"""
        
        try:
            # Отзыв всех refresh токенов пользователя
            revoked_count = await self.refresh_token_repo.revoke_user_tokens(user_id)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        
        # Инвалидация кеша токенов пользователя
        await self.redis_blacklist.invalidate_user_tokens_cache(user_id)
        # User-level отзыв access-токенов (видим во всех сервисах через shared/auth_lib)
        await self.redis_blacklist.revoke_all_user_tokens(user_id)

        logger.info(f"User {user_id} logged out from all devices ({revoked_count} tokens revoked)")
        
        return {"message": f"Logged out from {revoked_count} devices"}
    
    async def validate_access_token(self, access_token: str) -> TokenPayload:
        """Валидация access токена с Redis blacklist кешированием"""
        
        # Базовая проверка формата
        if not self.security.validate_token_format(access_token):
            raise InvalidTokenException()
        
        # Декодирование токена
        payload = self.security.decode_access_token(access_token)
        if not payload:
            raise InvalidTokenException()
        
        token_payload = TokenPayload(payload)
        
        # Проверка истечения
        if token_payload.is_expired:
            raise InvalidTokenException()
        
        # Проверка blacklist через Redis
        if await self.redis_blacklist.is_token_blacklisted(token_payload.jti):
            raise TokenBlacklistedException()
        
        return token_payload
    
    async def get_current_user(self, token_payload: TokenPayload) -> User:
        """Получение текущего пользователя по токену"""
        
        user = await self.user_repo.get_by_id(
            token_payload.user_id,
            relationships=["role"]
        )
        
        if not user:
            raise UserNotFoundException()
        
        if not user.is_active:
            raise UserInactiveException()
        
        return user
    
    async def cleanup_expired_tokens(self) -> Dict[str, int]:
        """Очистка истекших токенов и записей blacklist"""
        
        try:
            # Очистка БД
            expired_refresh_tokens = await self.refresh_token_repo.cleanup_expired_tokens()
            expired_blacklist_records = await self.blacklist_repo.cleanup_expired_blacklist()
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        
        # Очистка Redis кеша
        expired_cache_records = await self.redis_blacklist.cleanup_expired_cache()
        
        return {
            "expired_refresh_tokens": expired_refresh_tokens,
            "expired_blacklist_records": expired_blacklist_records,
            "expired_cache_records": expired_cache_records
        }
    
    async def get_auth_stats(self) -> Dict[str, Any]:
        """Получение статистики аутентификации"""
        
        try:
            # Статистика rate limiting
            rate_limit_stats = await self.rate_limiter.get_rate_limit_stats()
            
            # Статистика blacklist кеша
            blacklist_stats = await self.redis_blacklist.get_cache_stats()
            
            return {
                "rate_limiting": rate_limit_stats,
                "blacklist_cache": blacklist_stats,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get auth stats: {e}")
            return {"error": str(e)}