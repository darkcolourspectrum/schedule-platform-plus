from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from app.repositories.base import BaseRepository
from app.models.user import User
from app.models.refresh_token import RefreshToken, TokenBlacklist


class UserRepository(BaseRepository[User]):
    """Репозиторий для работы с пользователями"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """Получение пользователя по email с загрузкой роли и студии"""
        return await self.get_by_field(
            "email", 
            email, 
            relationships=["role"]
        )
    
    async def get_by_vk_id(self, vk_id: str) -> Optional[User]:
        """Получение пользователя по VK ID"""
        return await self.get_by_field(
            "vk_id", 
            vk_id, 
            relationships=["role"]
        )
    
    async def create_user(
        self,
        email: str,
        first_name: str,
        last_name: str,
        role_id: int,
        hashed_password: Optional[str] = None,
        phone: Optional[str] = None,
        studio_id: Optional[int] = None,
        vk_id: Optional[str] = None,
        oauth_provider: Optional[str] = None,
        privacy_policy_accepted: bool = False
    ) -> User:
        """Создание нового пользователя"""
        user_data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role_id": role_id,
            "privacy_policy_accepted": privacy_policy_accepted,
            "privacy_policy_accepted_at": datetime.utcnow() if privacy_policy_accepted else None
        }
        
        if hashed_password:
            user_data["hashed_password"] = hashed_password
        
        if phone:
            user_data["phone"] = phone
            
        if studio_id:
            user_data["studio_id"] = studio_id
            
        if vk_id:
            user_data["vk_id"] = vk_id
            
        if oauth_provider:
            user_data["oauth_provider"] = oauth_provider
        
        return await self.create(**user_data)
    
    async def update_last_login(self, user_id: int) -> None:
        """Обновление времени последнего входа"""
        await self.update(user_id, last_login=datetime.utcnow())
    
    async def increment_login_attempts(self, user_id: int) -> None:
        """Увеличение счетчика попыток входа"""
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()
        
        if user:
            new_attempts = user.login_attempts + 1
            await self.update(user_id, login_attempts=new_attempts)
    
    async def reset_login_attempts(self, user_id: int) -> None:
        """Сброс счетчика попыток входа"""
        await self.update(user_id, login_attempts=0, locked_until=None)
    
    async def lock_user_account(self, user_id: int, lock_duration_minutes: int = 30) -> None:
        """Блокировка аккаунта пользователя"""
        locked_until = datetime.utcnow() + timedelta(minutes=lock_duration_minutes)
        await self.update(user_id, locked_until=locked_until)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Репозиторий для работы с refresh токенами"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(RefreshToken, db)
    
    async def create_refresh_token(
        self,
        user_id: int,
        token: str,
        expires_at: datetime,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> RefreshToken:
        """Создание refresh токена"""
        return await self.create(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    async def get_by_token(self, token: str) -> Optional[RefreshToken]:
        """Получение refresh токена по значению с предзагрузкой user и role"""
        from sqlalchemy.orm import selectinload
        
        query = select(RefreshToken).where(RefreshToken.token == token).options(
            selectinload(RefreshToken.user).selectinload(User.role)
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def revoke_token(self, token: str) -> bool:
        """Отзыв refresh токена"""
        query = (
            update(RefreshToken)
            .where(RefreshToken.token == token)
            .values(is_revoked=True)
        )
        
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0
    
    async def revoke_user_tokens(self, user_id: int) -> int:
        """Отзыв всех токенов пользователя"""
        query = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(is_revoked=True)
        )
        
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount
    
    async def cleanup_expired_tokens(self) -> int:
        """Очистка истекших токенов"""
        from sqlalchemy import delete
        
        query = delete(RefreshToken).where(RefreshToken.expires_at < datetime.utcnow())
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount


class TokenBlacklistRepository(BaseRepository[TokenBlacklist]):
    """Репозиторий для работы с черным списком токенов"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(TokenBlacklist, db)
    
    async def add_to_blacklist(
        self,
        token_jti: str,
        token_type: str,
        expires_at: datetime,
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> TokenBlacklist:
        """Добавление токена в черный список"""
        return await self.create(
            token_jti=token_jti,
            token_type=token_type,
            expires_at=expires_at,
            user_id=user_id,
            reason=reason
        )
    
    async def is_blacklisted(self, token_jti: str) -> bool:
        """Проверка токена в черном списке"""
        return await self.exists(token_jti=token_jti)
    
    async def cleanup_expired_blacklist(self) -> int:
        """Очистка истекших записей из черного списка"""
        from sqlalchemy import delete
        
        query = delete(TokenBlacklist).where(TokenBlacklist.expires_at < datetime.utcnow())
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount