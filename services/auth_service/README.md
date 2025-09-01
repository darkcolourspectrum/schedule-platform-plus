# Auth Service - Микросервис аутентификации и авторизации

## Описание

Auth Service - это микросервис для управления аутентификацией, авторизацией пользователей и управления студиями в рамках платформы Schedule Platform Plus для вокальной школы.

## Возможности

### Основные функции
- Регистрация и аутентификация пользователей
- JWT токены (access/refresh)
- Управление ролями пользователей (admin, teacher, student, guest)
- Управление студиями
- Система разрешений и доступа
- Безопасность паролей с bcrypt
- Защита от брутфорса
- Blacklist токенов

### Роли пользователей
- **Admin** - Администратор с полными правами
- **Teacher** - Преподаватель с правами управления расписанием
- **Student** - Ученик с базовыми правами  
- **Guest** - Гость для пробных уроков

## Технологический стек

### Backend
- **FastAPI** 0.115.9 - веб-фреймворк
- **SQLAlchemy** 2.0.38 - ORM
- **Alembic** 1.14.1 - миграции БД
- **PostgreSQL** - основная база данных
- **Redis** 5.0.1 - кэширование и сессии

### Безопасность
- **python-jose** 3.4.0 - JWT токены
- **passlib** 1.7.4 - хэширование паролей
- **bcrypt** 4.1.3 - алгоритм хэширования
- **cryptography** 44.0.2 - криптографические операции

### Валидация и конфигурация
- **Pydantic** 2.10.6 - валидация данных
- **python-dotenv** 1.0.1 - управление конфигурацией

## Архитектура

```
auth_service/
├── app/                          # Основное приложение
│   ├── api/                      # API слой
│   │   ├── v1/                   # API версия 1
│   │   │   ├── auth.py           # Аутентификация endpoints
│   │   │   ├── users.py          # Управление пользователями
│   │   │   ├── roles.py          # Управление ролями
│   │   │   ├── studios.py        # Управление студиями
│   │   │   └── admin.py          # Админ панель endpoints
│   │   └── router.py             # Главный роутер
│   ├── core/                     # Ядро приложения
│   │   ├── security.py           # JWT и безопасность
│   │   ├── exceptions.py         # Кастомные исключения
│   │   ├── permissions.py        # Система разрешений
│   │   └── middleware.py         # Middleware
│   ├── database/                 # База данных
│   │   ├── connection.py         # Подключение к БД
│   │   └── redis_client.py       # Redis клиент
│   ├── models/                   # SQLAlchemy модели
│   │   ├── user.py               # Модель пользователя
│   │   ├── role.py               # Модель роли
│   │   ├── studio.py             # Модель студии
│   │   ├── refresh_token.py      # Модели токенов
│   │   └── base.py               # Базовая модель
│   ├── repositories/             # Слой доступа к данным
│   │   ├── base.py               # Базовый репозиторий
│   │   ├── user_repository.py    # Репозиторий пользователей
│   │   └── role_repository.py    # Репозиторий ролей
│   ├── services/                 # Бизнес-логика
│   │   ├── auth_service.py       # Сервис аутентификации
│   │   ├── user_service.py       # Сервис пользователей
│   │   ├── studio_service.py     # Сервис студий
│   │   └── email_service.py      # Email сервис
│   ├── schemas/                  # Pydantic схемы
│   │   ├── auth.py               # Схемы аутентификации
│   │   ├── user.py               # Схемы пользователей
│   │   ├── role.py               # Схемы ролей
│   │   └── admin.py              # Админ схемы
│   ├── dependencies.py           # FastAPI зависимости
│   ├── config.py                 # Конфигурация приложения
│   └── main.py                   # Точка входа приложения
├── migrations/                   # Alembic миграции
├── scripts/                      # Вспомогательные скрипты
├── tests/                        # Тесты
├── docker/                       # Docker конфигурация
├── requirements.txt              # Python зависимости
├── .env                          # Переменные окружения
└── README.md                     # Документация
```

## Установка и запуск

### Требования
- Python 3.11+
- PostgreSQL 13+
- Redis 6+ (опционально)

### 1. Клонирование и установка зависимостей

```bash
cd services/auth_service
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Настройка конфигурации

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Основные настройки в `.env`:

```env
# Database
DATABASE_URL=postgresql://username:password@localhost:5432/auth_service_db

# JWT
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Redis (опционально)
REDIS_URL=redis://localhost:6379/0

# Application
DEBUG=True
ENVIRONMENT=development
```

### 3. Подготовка базы данных

```bash
# Создание БД и применение миграций
alembic upgrade head

# Инициализация ролей и тестовых данных
python scripts/init_database.py
```

### 4. Запуск приложения

```bash
# Разработка
python run_server.py

# Или через uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Проверка работы

- **Swagger UI**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **ReDoc**: http://localhost:8000/redoc

## API Documentation

### Аутентификация (/api/v1/auth)

#### POST /api/v1/auth/register
Регистрация нового пользователя

**Request:**
```json
{
  "email": "user@example.com",
  "password": "password123",
  "first_name": "Имя",
  "last_name": "Фамилия",
  "phone": "+79001234567",
  "privacy_policy_accepted": true
}
```

**Response (201):**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "role": "student",
    "studio_id": null,
    "studio_name": null,
    "is_active": true,
    "is_verified": false
  },
  "tokens": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "550e8400-e29b-41d4-a716-446655440000",
    "token_type": "bearer"
  }
}
```

#### POST /api/v1/auth/login
Аутентификация пользователя

**Request:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response (200):**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "role": "student",
    "studio_id": null,
    "studio_name": null,
    "is_active": true,
    "is_verified": false
  },
  "tokens": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "550e8400-e29b-41d4-a716-446655440000",
    "token_type": "bearer"
  }
}
```

#### POST /api/v1/auth/refresh
Обновление access токена

**Headers:**
```
Cookie: refresh_token=550e8400-e29b-41d4-a716-446655440000
```

**Response (200):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

#### POST /api/v1/auth/logout
Выход из системы

**Headers:**
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response (200):**
```json
{
  "message": "Successfully logged out"
}
```

#### GET /api/v1/auth/me
Получение информации о текущем пользователе

**Headers:**
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Имя",
  "last_name": "Фамилия",
  "full_name": "Имя Фамилия",
  "role": "student",
  "studio_id": null,
  "studio_name": null,
  "is_admin": false,
  "is_teacher": false,
  "is_student": true,
  "permissions": []
}
```

### Пользователи (/api/v1/users)

#### GET /api/v1/users
Получение списка пользователей (только для администраторов)

**Query Parameters:**
- `limit` (int, default=50): Количество пользователей
- `offset` (int, default=0): Смещение
- `role` (str, optional): Фильтр по роли
- `studio_id` (int, optional): Фильтр по студии

**Headers:**
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response (200):**
```json
[
  {
    "id": 1,
    "email": "user@example.com",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "role": "student",
    "studio_name": null,
    "is_active": true,
    "created_at": "2024-01-15T10:00:00Z",
    "last_login": "2024-01-15T12:00:00Z"
  }
]
```

### Студии (/api/v1/studios)

#### GET /api/v1/studios
Получение списка студий

**Headers:**
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response (200):**
```json
[
  {
    "id": 1,
    "name": "Главная студия",
    "description": "Основная студия вокальной школы",
    "address": "г. Москва, ул. Примерная, д. 1",
    "phone": "+7 (900) 123-45-67",
    "email": "info@studio.com",
    "is_active": true,
    "teachers_count": 5,
    "students_count": 25,
    "created_at": "2024-01-01T10:00:00Z"
  }
]
```

## Тестирование

### Запуск интеграционных тестов

```bash
# Убедитесь, что сервер запущен
python run_server.py

# В другом терминале запустите тесты
python run_tests.py
```

### Тестируемые сценарии

- ✅ Health endpoints
- ✅ Регистрация пользователей
- ✅ Обработка дубликатов email
- ✅ Валидация входных данных
- ✅ Аутентификация пользователей
- ✅ Обработка неверных данных входа
- ✅ Защищенные endpoints
- ✅ Валидация JWT токенов
- ✅ Выход из системы
- ✅ Автоматическая очистка тестовых данных

### Юнит-тесты

```bash
# Запуск pytest тестов
pytest tests/ -v --cov=app --cov-report=html
```

## Безопасность

### JWT Токены
- **Access Token**: Время жизни 30 минут (настраивается)
- **Refresh Token**: Время жизни 7 дней (настраивается)
- **Алгоритм**: HS256
- **Blacklist**: Отозванные токены хранятся в БД

### Пароли
- **Хэширование**: bcrypt с 12 раундами
- **Требования**: Минимум 8 символов, буквы и цифры
- **Защита от брутфорса**: Блокировка аккаунта после 5 неудачных попыток

### CORS
- Настраиваемые разрешенные origin'ы
- Поддержка cookies для refresh токенов

## База данных

### Модели

#### users
- Основная информация о пользователях
- Связь с ролями и студиями
- Поля безопасности (login_attempts, locked_until)

#### roles
- Система ролей (admin, teacher, student, guest)
- Описания ролей

#### studios
- Информация о студиях
- Контактные данные

#### refresh_tokens
- Хранение refresh токенов
- Информация об устройствах
- Отслеживание сессий

#### token_blacklist
- Черный список отозванных токенов
- Автоматическая очистка истекших записей

### Миграции

```bash
# Создание новой миграции
alembic revision --autogenerate -m "Описание изменений"

# Применение миграций
alembic upgrade head

# Откат миграции
alembic downgrade -1
```

## Мониторинг и логирование

### Health Checks
- `GET /health` - статус сервиса
- `GET /` - общая информация о сервисе

### Логирование
- Структурированные логи
- Уровни: INFO, WARNING, ERROR
- Логирование аутентификации и ошибок безопасности

## Развертывание

### Docker

```bash
# Сборка образа
docker build -f docker/Dockerfile -t auth-service .

# Запуск с docker-compose
docker-compose -f docker/docker-compose.yml up -d
```

### Environment Variables

Все настройки управляются через переменные окружения:

```env
# Обязательные
DATABASE_URL=postgresql://...
JWT_SECRET_KEY=your-secret-key

# Опциональные
DEBUG=False
ENVIRONMENT=production
REDIS_URL=redis://...
CORS_ORIGINS=["https://yourdomain.com"]
```

## Планы развития

### Ближайшие фичи
- [ ] Email верификация
- [ ] OAuth интеграция (VK, Google)
- [ ] Двухфакторная аутентификация
- [ ] Rate limiting
- [ ] Аудит логи

### Интеграции
- [ ] Notification Service
- [ ] File Storage Service
- [ ] Analytics Service

## Поддержка

### Диагностика проблем

```bash
# Проверка подключения к БД
python -m app.database.connection

# Проверка Redis (если используется)
python -m app.database.redis_client

# Отладка регистрации
python debug_registration.py

# Проверка маршрутов
python test_fastapi_routes.py
```

### Типичные проблемы

1. **Ошибка подключения к БД**
   - Проверьте настройки в `.env`
   - Убедитесь, что PostgreSQL запущен
   - Проверьте права доступа

2. **JWT токены не работают**
   - Проверьте `JWT_SECRET_KEY` в `.env`
   - Убедитесь, что время системы синхронизировано

3. **Ошибки валидации**
   - Проверьте формат входных данных
   - Убедитесь, что все обязательные поля заполнены

## Контакты

Для вопросов по разработке и интеграции обращайтесь к команде разработки Schedule Platform Plus.

---

*Документация обновлена: 1 сентября 2025*