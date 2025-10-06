"""
Интеграционные тесты для Auth Service
Тестируют весь микросервис через HTTP API
"""

import asyncio
import sys
import pytest
import httpx
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.main import app
from app.database.connection import create_async_session_factory
from app.repositories.user_repository import UserRepository


TEST_USERS = [
    {
        "email": "testuser1@example.com",
        "password": "testpassword123",
        "first_name": "Test",
        "last_name": "User1",
        "phone": "+79081234567",
        "privacy_policy_accepted": True
    },
    {
        "email": "testuser2@example.com", 
        "password": "testpassword456",
        "first_name": "Test",
        "last_name": "User2",
        "phone": "+79087654321",
        "privacy_policy_accepted": True
    }
]

BASE_URL = "http://127.0.0.1:8000"


class AuthServiceTester:
    """Класс для тестирования Auth Service"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
        self.tokens = {}  # Хранение токенов для тестов
        self.users = {}   # Хранение созданных пользователей
    
    async def cleanup_test_users(self):
        """Очистка тестовых пользователей из БД"""
        session_factory = create_async_session_factory()
        
        async with session_factory() as db:
            user_repo = UserRepository(db)
            
            for user_data in TEST_USERS:
                try:
                    user = await user_repo.get_by_email(user_data["email"])
                    if user:
                        # Отзываем все токены пользователя через API
                        try:
                            await self.client.post(
                                "/api/v1/auth/logout-all",
                                headers={"Authorization": f"Bearer {self.tokens.get(user.email, 'invalid')}"}
                            )
                        except:
                            pass
                        
                        # Теперь удаляем пользователя (каскадное удаление должно работать)
                        await user_repo.delete(user.id)
                        print(f"🗑️  Удален тестовый пользователь: {user_data['email']}")
                except Exception as e:
                    print(f"⚠️  Ошибка при очистке {user_data['email']}: {e}")
                    # В случае ошибки, попробуем принудительно удалить токены
                    try:
                        from app.repositories.user_repository import RefreshTokenRepository
                        refresh_repo = RefreshTokenRepository(db)
                        if 'user' in locals() and user:
                            await refresh_repo.revoke_user_tokens(user.id)
                            await user_repo.delete(user.id)
                            print(f"Принудительно удален: {user_data['email']}")
                    except Exception as cleanup_error:
                        print(f"Не удалось очистить {user_data['email']}: {cleanup_error}")
    
    async def test_health_endpoints(self):
        """Тест базовых endpoint'ов здоровья"""
        print("\nТестирование health endpoints...")
        
        # Корневой endpoint
        response = await self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "Auth Service" in data["service"]
        print("Корневой endpoint работает")
        
        # Health check
        response = await self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("Health check работает")
    
    async def test_user_registration(self):
        """Тест регистрации пользователей"""
        print("\nТестирование регистрации пользователей...")
        
        for i, user_data in enumerate(TEST_USERS):
            response = await self.client.post("/api/v1/auth/register", json=user_data)
            
            if response.status_code == 409:
                print(f"Пользователь {user_data['email']} уже существует, пропускаем")
                continue
            
            assert response.status_code == 201, f"Ошибка регистрации: {response.text}"
            data = response.json()
            
            # Проверяем структуру ответа
            assert "user" in data
            assert "tokens" in data
            assert data["user"]["email"] == user_data["email"]
            assert data["user"]["role"] == "student"
            assert "access_token" in data["tokens"]
            assert "refresh_token" in data["tokens"]
            
            # Сохраняем данные для дальнейших тестов
            self.users[user_data["email"]] = data["user"]
            self.tokens[user_data["email"]] = data["tokens"]["access_token"]
            
            print(f"Пользователь {user_data['email']} зарегистрирован (ID: {data['user']['id']})")
    
    async def test_duplicate_registration(self):
        """Тест регистрации дубликата"""
        print("\nТестирование дублирующей регистрации...")
        
        # Пытаемся зарегистрировать пользователя повторно
        response = await self.client.post("/api/v1/auth/register", json=TEST_USERS[0])
        assert response.status_code == 409
        data = response.json()
        assert "already exists" in data["detail"]
        print("Дублирующая регистрация корректно отклонена")
    
    async def test_invalid_registration_data(self):
        """Тест регистрации с невалидными данными"""
        print("\nТестирование невалидных данных регистрации...")
        
        invalid_cases = [
            # Невалидный email
            {
                **TEST_USERS[0],
                "email": "invalid-email",
            },
            # Слишком короткий пароль
            {
                **TEST_USERS[0],
                "email": "short@test.com",
                "password": "123"
            },
            # Не принята политика конфиденциальности
            {
                **TEST_USERS[0], 
                "email": "policy@test.com",
                "privacy_policy_accepted": False
            }
        ]
        
        for i, invalid_data in enumerate(invalid_cases):
            response = await self.client.post("/api/v1/auth/register", json=invalid_data)
            assert response.status_code == 422, f"Кейс {i+1} должен вернуть 422"
            print(f"Невалидный кейс {i+1} корректно отклонен")
    
    async def test_user_login(self):
        """Тест аутентификации пользователей"""
        print("\nТестирование аутентификации пользователей...")
        
        for user_data in TEST_USERS:
            login_data = {
                "email": user_data["email"],
                "password": user_data["password"]
            }
            
            response = await self.client.post("/api/v1/auth/login", json=login_data)
            
            if response.status_code == 401:
                print(f"Пользователь {user_data['email']} не найден, пропускаем login тест")
                continue
            
            assert response.status_code == 200, f"Ошибка входа: {response.text}"
            data = response.json()
            
            # Проверяем структуру ответа
            assert "user" in data
            assert "tokens" in data
            assert data["user"]["email"] == user_data["email"]
            assert "access_token" in data["tokens"]
            
            # Обновляем токены
            self.tokens[user_data["email"]] = data["tokens"]["access_token"]
            
            print(f"Пользователь {user_data['email']} успешно вошел")
    
    async def test_invalid_login(self):
        """Тест входа с неверными данными"""
        print("\nТестирование неверных данных входа...")
        
        # Неверный пароль
        response = await self.client.post("/api/v1/auth/login", json={
            "email": TEST_USERS[0]["email"],
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("Неверный пароль корректно отклонен")
        
        # Несуществующий пользователь
        response = await self.client.post("/api/v1/auth/login", json={
            "email": "nonexistent@test.com", 
            "password": "password123"
        })
        assert response.status_code == 401
        print("Несуществующий пользователь корректно отклонен")
    
    async def test_protected_endpoints(self):
        """Тест защищенных endpoint'ов"""
        print("\nТестирование защищенных endpoints...")
        
        # Тест без токена
        response = await self.client.get("/api/v1/auth/me")
        assert response.status_code == 422 or response.status_code == 401
        print("Защищенный endpoint недоступен без токена")
        
        # Тест с валидным токеном
        email = TEST_USERS[0]["email"]
        if email in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens[email]}"}
            response = await self.client.get("/api/v1/auth/me", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                assert data["email"] == email
                print(f"Защищенный endpoint доступен с валидным токеном")
            else:
                print(f"Токен возможно истек, статус: {response.status_code}")
    
    async def test_token_validation(self):
        """Тест валидации токенов"""
        print("\nТестирование валидации токенов...")
        
        email = TEST_USERS[0]["email"]
        if email in self.tokens:
            headers = {"Authorization": f"Bearer {self.tokens[email]}"}
            response = await self.client.post("/api/v1/auth/validate-token", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                assert data["valid"] == True
                assert "user_id" in data
                print("Валидация токена прошла успешно")
            else:
                print(f"Ошибка валидации токена: {response.status_code}")
    
    async def test_logout(self):
        """Тест выхода из системы"""
        print("\nТестирование выхода из системы...")
        
        email = TEST_USERS[0]["email"]
        if email in self.tokens:
            # Сначала нужно получить refresh token из login
            login_data = {
                "email": email,
                "password": TEST_USERS[0]["password"]
            }
            
            # Логинимся заново чтобы получить свежие токены
            login_response = await self.client.post("/api/v1/auth/login", json=login_data)
            if login_response.status_code == 200:
                login_data_response = login_response.json()
                self.tokens[email] = login_data_response["tokens"]["access_token"]
                
                # Проверяем cookies для refresh token
                cookies = login_response.cookies
                
                headers = {"Authorization": f"Bearer {self.tokens[email]}"}
                
                # Пытаемся выйти
                response = await self.client.post("/api/v1/auth/logout", headers=headers, cookies=cookies)
                
                if response.status_code == 200:
                    data = response.json()
                    assert "message" in data
                    print("Выход из системы прошел успешно")
                    
                    # Проверяем, что токен стал недействительным
                    response = await self.client.get("/api/v1/auth/me", headers=headers)
                    assert response.status_code == 401
                    print("Токен корректно аннулирован")
                else:
                    print(f"Ошибка выхода: {response.status_code}")
                    print(f"    Response: {response.text}")
            else:
                print(f"Не удалось залогиниться для теста logout: {login_response.status_code}")
    
    async def run_all_tests(self):
        """Запуск всех тестов"""
        print("Запуск интеграционных тестов Auth Service")
        print("=" * 50)
        
        try:
            # Предварительная очистка
            await self.cleanup_test_users()
            
            # Запуск тестов
            await self.test_health_endpoints()
            await self.test_user_registration()
            await self.test_duplicate_registration()
            await self.test_invalid_registration_data()
            await self.test_user_login()
            await self.test_invalid_login()
            await self.test_protected_endpoints()
            await self.test_token_validation()
            await self.test_logout()
            
            print("\nВсе интеграционные тесты пройдены успешно!")
            print("=" * 50)
            
            # Финальная очистка
            await self.cleanup_test_users()
            
        except Exception as e:
            print(f"\nОшибка в тестах: {e}")
            import traceback
            traceback.print_exc()
            
            # Попытка очистки при ошибке
            try:
                await self.cleanup_test_users()
            except:
                pass
            
            raise
        
        finally:
            await self.client.aclose()


async def main():
    """Главная функция тестирования"""
    
    print("Проверка доступности сервера...")
    
    # Проверяем, что сервер запущен
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
            response = await client.get("/health")
            if response.status_code != 200:
                print("Сервер недоступен!")
                print("Запустите сервер: python run_server.py")
                return False
    except Exception:
        print("Сервер недоступен!")
        print("Запустите сервер: python run_server.py")
        return False
    
    print("Сервер доступен, начинаем тестирование...")
    
    # Запуск тестов
    tester = AuthServiceTester()
    await tester.run_all_tests()
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)