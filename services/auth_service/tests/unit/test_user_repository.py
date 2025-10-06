"""
Модульные тесты для app/repositories/user_repository.py
Тестируем методы репозитория пользователей с моками базы данных
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from app.repositories.user_repository import UserRepository
from app.models.user import User
from app.models.role import Role


@pytest.fixture
def mock_db():
    """Фикстура: мок для AsyncSession базы данных"""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def user_repository(mock_db):
    """Фикстура: экземпляр UserRepository с моком БД"""
    return UserRepository(mock_db)


@pytest.fixture
def fake_role():
    """Фикстура: роль студента"""
    role = MagicMock(spec=Role)
    role.id = 2
    role.name = "student"
    role.description = "Student role"
    return role


@pytest.fixture
def fake_user(fake_role):
    """Фикстура: пользователь"""
    user = MagicMock(spec=User)
    user.id = 1
    user.email = "test@example.com"
    user.first_name = "Test"
    user.last_name = "User"
    user.hashed_password = "hashed_password_123"
    user.role_id = 2
    user.role = fake_role
    user.studio_id = None
    user.is_active = True
    user.is_verified = False
    user.is_locked = False
    user.login_attempts = 0
    user.locked_until = None
    user.last_login = None
    user.created_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    return user


class TestUserRepositoryCreate:
    """Тесты для метода create_user"""
    
    @pytest.mark.asyncio
    async def test_create_user_with_valid_data(self, user_repository, mock_db, fake_user):
        """Тест 1: Создание пользователя с валидными данными"""
        # Arrange
        mock_db.refresh.side_effect = lambda obj: setattr(obj, 'id', 1)
        
        # Act
        result = await user_repository.create_user(
            email="newuser@example.com",
            first_name="New",
            last_name="User",
            role_id=2,
            hashed_password="hashed_pass",
            phone="+79001234567",
            privacy_policy_accepted=True
        )
        
        # Assert
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_create_user_with_duplicate_email_raises_error(
        self, user_repository, mock_db
    ):
        """Тест 2: Создание пользователя с существующим email вызывает ошибку"""
        # Arrange
        mock_db.commit.side_effect = IntegrityError(
            "duplicate key", None, None
        )
        
        # Act & Assert
        with pytest.raises(IntegrityError):
            await user_repository.create_user(
                email="existing@example.com",
                first_name="Test",
                last_name="User",
                role_id=2,
                hashed_password="hashed",
                privacy_policy_accepted=True
            )
    
    @pytest.mark.asyncio
    async def test_create_user_without_phone_succeeds(
        self, user_repository, mock_db
    ):
        """Тест 3: Создание пользователя без телефона (опциональное поле)"""
        # Arrange
        mock_db.refresh.side_effect = lambda obj: setattr(obj, 'id', 5)
        
        # Act
        result = await user_repository.create_user(
            email="nophone@example.com",
            first_name="No",
            last_name="Phone",
            role_id=2,
            hashed_password="hashed",
            phone=None,
            privacy_policy_accepted=True
        )
        
        # Assert
        assert mock_db.add.called
        assert mock_db.commit.called


class TestUserRepositoryGetByEmail:
    """Тесты для метода get_by_email"""
    
    @pytest.mark.asyncio
    async def test_get_by_email_returns_user_when_exists(
        self, user_repository, mock_db, fake_user
    ):
        """Тест 4: Поиск существующего пользователя по email"""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result
        
        # Act
        result = await user_repository.get_by_email("test@example.com")
        
        # Assert
        assert result is not None
        assert result.email == "test@example.com"
        assert mock_db.execute.called
    
    @pytest.mark.asyncio
    async def test_get_by_email_returns_none_when_not_exists(
        self, user_repository, mock_db
    ):
        """Тест 5: Поиск несуществующего пользователя возвращает None"""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        # Act
        result = await user_repository.get_by_email("notfound@example.com")
        
        # Assert
        assert result is None
        assert mock_db.execute.called
    
    @pytest.mark.asyncio
    async def test_get_by_email_with_empty_email(
        self, user_repository, mock_db
    ):
        """Тест 6: Поиск по пустому email возвращает None"""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        # Act
        result = await user_repository.get_by_email("")
        
        # Assert
        assert result is None


class TestUserRepositoryUpdate:
    """Тесты для метода update"""
    
    @pytest.mark.asyncio
    async def test_update_user_first_name(
        self, user_repository, mock_db, fake_user
    ):
        """Тест 7: Обновление имени пользователя"""
        # Arrange - update() использует UPDATE запрос напрямую, возвращает через .returning()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result
        
        # Act
        result = await user_repository.update(1, first_name="Updated")
        
        # Assert
        assert mock_db.execute.called  # UPDATE запрос был выполнен
        assert mock_db.commit.called    # Коммит был вызван
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_user_returns_none(
        self, user_repository, mock_db
    ):
        """Тест 8: Обновление несуществующего пользователя возвращает None"""
        # Arrange - UPDATE вернет None если запись не найдена
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        # Act
        result = await user_repository.update(999, first_name="New")
        
        # Assert
        assert result is None
        assert mock_db.commit.called  # commit вызывается в любом случае


class TestUserRepositoryLoginAttempts:
    """Тесты для методов управления попытками входа"""
    
    @pytest.mark.asyncio
    async def test_increment_login_attempts(
        self, user_repository, mock_db, fake_user
    ):
        """Тест 9: Увеличение счетчика неудачных попыток входа"""
        # Arrange - increment делает get, потом update
        fake_user.login_attempts = 2
        
        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = fake_user
        
        mock_result_update = MagicMock()
        mock_result_update.scalar_one_or_none.return_value = fake_user
        
        # Первый вызов - get пользователя, второй - update query
        mock_db.execute.side_effect = [mock_result_get, mock_result_update]
        
        # Act
        await user_repository.increment_login_attempts(1)
        
        # Assert
        assert mock_db.commit.called
        assert mock_db.execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_reset_login_attempts(
        self, user_repository, mock_db, fake_user
    ):
        """Тест 10: Сброс счетчика попыток входа"""
        fake_user.login_attempts = 0
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result
        
        # Act
        await user_repository.reset_login_attempts(1)
        
        # Assert
        assert mock_db.commit.called
        assert mock_db.execute.call_count == 1  
    
    @pytest.mark.asyncio
    async def test_lock_user_account(
        self, user_repository, mock_db, fake_user
    ):
        """Тест 11: Блокировка аккаунта пользователя"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result
        
        # Act
        await user_repository.lock_user_account(1, lock_duration_minutes=30)
        
        # Assert
        assert mock_db.commit.called
        assert mock_db.execute.call_count == 1  


class TestUserRepositoryUpdateLastLogin:
    """Тест для метода обновления последнего входа"""
    
    @pytest.mark.asyncio
    async def test_update_last_login(
        self, user_repository, mock_db, fake_user
    ):
        """Тест 12: Обновление времени последнего входа"""
        fake_user.last_login = datetime.utcnow()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result
        
        # Act
        await user_repository.update_last_login(1)
        
        # Assert
        assert mock_db.commit.called
        assert mock_db.execute.call_count == 1  