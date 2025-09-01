"""
Тесты для Redis интеграции: JWT blacklist и rate limiting
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx
from datetime import datetime, timedelta

from app.database.connection import create_async_session_factory
from app.services.redis_blacklist_service import RedisBlacklistService
from app.services.redis_rate_limiter import AuthRateLimiter
from app.database.redis_client import redis_client

BASE_URL = "http://127.0.0.1:8000"


class RedisIntegrationTester:
    """Класс для тестирования Redis интеграции"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
        self.test_email = "redis_test@example.com"
    
    async def test_redis_connection(self) -> bool:
        """Тест подключения к Redis"""
        print("\n🔍 Тестирование подключения к Redis...")
        
        try:
            success = await redis_client.test_connection()
            if success:
                print("✅ Redis доступен")
                return True
            else:
                print("❌ Redis недоступен")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка подключения к Redis: {e}")
            return False
    
    async def test_blacklist_caching(self) -> bool:
        """Тест кеширования JWT blacklist"""
        print("\n🚫 Тестирование JWT blacklist кеширования...")
        
        try:
            session_factory = create_async_session_factory()
            
            async with session_factory() as db:
                blacklist_service = RedisBlacklistService(db)
                
                # Тестовый токен JTI
                test_jti = "test-jwt-id-12345"
                
                # 1. Проверяем, что токен не в blacklist
                is_blacklisted_1 = await blacklist_service.is_token_blacklisted(test_jti)
                print(f"   Первая проверка (должно быть False): {is_blacklisted_1}")
                
                if is_blacklisted_1:
                    print("❌ Ошибка: токен не должен быть в blacklist")
                    return False
                
                # 2. Добавляем токен в blacklist
                expires_at = datetime.utcnow() + timedelta(hours=1)
                await blacklist_service.add_token_to_blacklist(
                    token_jti=test_jti,
                    token_type="access",
                    expires_at=expires_at,
                    reason="test"
                )
                print("   Токен добавлен в blacklist")
                
                # 3. Проверяем через кеш (должно быть быстро)
                start_time = time.time()
                is_blacklisted_2 = await blacklist_service.is_token_blacklisted(test_jti)
                cache_time = time.time() - start_time
                
                print(f"   Вторая проверка (должно быть True): {is_blacklisted_2}")
                print(f"   Время проверки через кеш: {cache_time:.4f}s")
                
                if not is_blacklisted_2:
                    print("❌ Ошибка: токен должен быть в blacklist")
                    return False
                
                # 4. Очистка
                await blacklist_service.remove_token_from_cache(test_jti)
                print("   Токен удален из кеша")
                
                print("✅ JWT blacklist кеширование работает корректно")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка тестирования blacklist: {e}")
            return False
    
    async def test_rate_limiting(self) -> bool:
        """Тест rate limiting"""
        print("\n⏱️  Тестирование rate limiting...")
        
        try:
            rate_limiter = AuthRateLimiter()
            test_ip = "192.168.1.100"
            
            # 1. Тестируем rate limiting для входа
            print("   Тестируем rate limiting для входа...")
            
            # Должно пройти несколько раз
            for i in range(3):
                try:
                    await rate_limiter.check_login_rate_limit(self.test_email, test_ip)
                    print(f"     Попытка {i+1}: разрешена")
                except Exception as e:
                    print(f"     Попытка {i+1}: заблокирована ({e})")
                    return False
            
            # 2. Проверяем превышение лимита
            print("   Проверяем превышение лимита...")
            blocked_attempts = 0
            
            for i in range(10):
                try:
                    await rate_limiter.check_login_rate_limit(self.test_email, test_ip)
                    print(f"     Попытка {i+4}: разрешена")
                except Exception:
                    blocked_attempts += 1
                    print(f"     Попытка {i+4}: заблокирована")
            
            if blocked_attempts > 0:
                print(f"✅ Rate limiting работает: {blocked_attempts} попыток заблокировано")
                
                # 3. Сбрасываем лимит
                await rate_limiter.reset_failed_login_attempts(self.test_email, test_ip)
                print("   Rate limit сброшен")
                
                return True
            else:
                print("❌ Rate limiting не сработал")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка тестирования rate limiting: {e}")
            return False
    
    async def test_end_to_end_performance(self) -> bool:
        """Тест производительности end-to-end"""
        print("\n🚀 Тестирование производительности...")
        
        try:
            # 1. Регистрируем тестового пользователя
            register_data = {
                "email": self.test_email,
                "password": "testpassword123",
                "first_name": "Redis",
                "last_name": "Test",
                "phone": "+79001234567",
                "privacy_policy_accepted": True
            }
            
            # Удаляем если уже существует
            try:
                session_factory = create_async_session_factory()
                async with session_factory() as db:
                    from app.repositories.user_repository import UserRepository
                    user_repo = UserRepository(db)
                    user = await user_repo.get_by_email(self.test_email)
                    if user:
                        await user_repo.delete(user.id)
                        print("   Удален существующий тестовый пользователь")
            except:
                pass
            
            # Регистрируем
            response = await self.client.post("/api/v1/auth/register", json=register_data)
            
            if response.status_code != 201:
                print(f"❌ Ошибка регистрации: {response.status_code}")
                return False
            
            data = response.json()
            access_token = data["tokens"]["access_token"]
            
            print("   Пользователь зарегистрирован")
            
            # 2. Тестируем скорость валидации токена
            headers = {"Authorization": f"Bearer {access_token}"}
            
            # Первый запрос (попадание в кеш)
            start_time = time.time()
            response1 = await self.client.get("/api/v1/auth/me", headers=headers)
            first_request_time = time.time() - start_time
            
            # Второй запрос (из кеша)
            start_time = time.time()
            response2 = await self.client.get("/api/v1/auth/me", headers=headers)
            second_request_time = time.time() - start_time
            
            print(f"   Первый запрос: {first_request_time:.4f}s")
            print(f"   Второй запрос: {second_request_time:.4f}s")
            
            if response1.status_code == 200 and response2.status_code == 200:
                speedup = first_request_time / second_request_time if second_request_time > 0 else 1
                print(f"   Ускорение: {speedup:.2f}x")
                
                if speedup > 1.1:  # Хотя бы 10% ускорение
                    print("✅ Кеширование дает прирост производительности")
                else:
                    print("⚠️  Прирост производительности минимален")
                
                # 3. Тестируем logout с blacklist
                logout_response = await self.client.post("/api/v1/auth/logout", headers=headers)
                
                if logout_response.status_code == 200:
                    print("   Logout выполнен, токен добавлен в blacklist")
                    
                    # 4. Проверяем, что токен заблокирован
                    blocked_response = await self.client.get("/api/v1/auth/me", headers=headers)
                    
                    if blocked_response.status_code == 401:
                        print("✅ Токен успешно заблокирован через Redis")
                        return True
                    else:
                        print("❌ Токен не заблокирован")
                        return False
                else:
                    print(f"❌ Ошибка logout: {logout_response.status_code}")
                    return False
            else:
                print("❌ Ошибка валидации токена")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка end-to-end теста: {e}")
            return False
        finally:
            # Очистка
            try:
                session_factory = create_async_session_factory()
                async with session_factory() as db:
                    from app.repositories.user_repository import UserRepository
                    user_repo = UserRepository(db)
                    user = await user_repo.get_by_email(self.test_email)
                    if user:
                        await user_repo.delete(user.id)
            except:
                pass
    
    async def run_all_tests(self) -> bool:
        """Запуск всех тестов Redis интеграции"""
        print("🧪 Тестирование Redis интеграции для Auth Service")
        print("=" * 50)
        
        try:
            # Проверка Redis
            redis_ok = await self.test_redis_connection()
            if not redis_ok:
                print("❌ Redis недоступен - тесты не могут быть выполнены")
                return False
            
            # Тест blacklist кеширования
            blacklist_ok = await self.test_blacklist_caching()
            
            # Тест rate limiting
            rate_limit_ok = await self.test_rate_limiting()
            
            # End-to-end тест
            e2e_ok = await self.test_end_to_end_performance()
            
            all_passed = blacklist_ok and rate_limit_ok and e2e_ok
            
            print("\n" + "=" * 50)
            print("📊 Результаты тестирования:")
            print(f"   JWT Blacklist кеширование: {'✅' if blacklist_ok else '❌'}")
            print(f"   Rate Limiting: {'✅' if rate_limit_ok else '❌'}")
            print(f"   End-to-End производительность: {'✅' if e2e_ok else '❌'}")
            
            if all_passed:
                print("\n🎉 Все тесты Redis интеграции пройдены!")
                print("💡 JWT blacklist кеширование и rate limiting работают корректно")
            else:
                print("\n⚠️  Некоторые тесты Redis не пройдены")
            
            return all_passed
            
        finally:
            await self.client.aclose()
            await redis_client.disconnect()


async def main():
    """Главная функция тестирования"""
    
    print("🚀 Проверка доступности сервера...")
    
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
            response = await client.get("/health")
            if response.status_code != 200:
                print("❌ Сервер недоступен!")
                print("💡 Запустите сервер: python run_server.py")
                return False
    except Exception:
        print("❌ Сервер недоступен!")
        print("💡 Запустите сервер: python run_server.py")
        return False
    
    print("✅ Сервер доступен\n")
    
    tester = RedisIntegrationTester()
    return await tester.run_all_tests()


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)