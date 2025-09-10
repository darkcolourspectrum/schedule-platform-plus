# 🐳 Docker Setup для Schedule Platform Plus

## 🏗️ Архитектура

### Микросервисы:
- **Auth Service** (порт 8000) - аутентификация и авторизация
- **Profile Service** (порт 8002) - профили пользователей  
- **Schedule Service** (порт 8001) - расписание и уроки

### Базы данных (изолированные):
- **auth_service_db** → пользователь: auth_user
- **profile_service_db** → пользователь: profile_user
- **schedule_service_db** → пользователь: schedule_user

### Общие сервисы:
- **PostgreSQL** (порт 5432) - основная БД
- **Redis** (порт 6379) - кэширование

## 🚀 Быстрый запуск

```bash
# Перейдите в корневую папку проекта
cd schedule-platform-plus

# Сделайте скрипт исполняемым (Linux/Mac)
chmod +x scripts/start-services.sh
chmod +x scripts/stop-services.sh

# Запустите все сервисы
./scripts/start-services.sh

# Или для Windows
docker-compose up -d
```

## 📋 Пошаговая инструкция

### 1. Подготовка
```bash
# Убедитесь что Docker Desktop запущен
docker --version
docker-compose --version
```

### 2. Создание структуры
```bash
# Создайте папку для инициализации БД
mkdir -p docker

# Убедитесь что файлы на месте:
# - docker-compose.yml
# - docker/init-databases.sql
# - services/*/Dockerfile
```

### 3. Первый запуск
```bash
# Запуск баз данных
docker-compose up -d postgres redis

# Ждем пока базы поднимутся (30 сек)
sleep 30

# Применяем миграции для каждого сервиса
docker-compose run --rm auth-service alembic upgrade head
docker-compose run --rm profile-service alembic upgrade head  
docker-compose run --rm schedule-service alembic upgrade head

# Запускаем все сервисы
docker-compose up -d
```

### 4. Проверка работоспособности
```bash
# Проверим статус всех контейнеров
docker-compose ps

# Проверим логи
docker-compose logs auth-service
docker-compose logs profile-service
docker-compose logs schedule-service

# Health checks
curl http://localhost:8000/health
curl http://localhost:8002/health
curl http://localhost:8001/health
```

## 🛠️ Управление

### Просмотр логов
```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f auth-service
docker-compose logs -f profile-service
docker-compose logs -f schedule-service
```

### Перезапуск сервиса
```bash
# Пересборка и перезапуск
docker-compose up -d --build auth-service

# Только перезапуск
docker-compose restart profile-service
```

### Остановка
```bash
# Остановка всех сервисов
docker-compose down

# С удалением volumes (ОСТОРОЖНО!)
docker-compose down -v
```

## 🔧 Инструменты разработчика

### PgAdmin (http://localhost:5050)
- **Email:** admin@example.com  
- **Password:** admin

**Настройка подключения к БД:**
- **Host:** postgres (имя контейнера)
- **Port:** 5432
- **Username:** auth_user / profile_user / schedule_user
- **Password:** auth_password / profile_password / schedule_password

### Redis Commander (http://localhost:8081)
- Автоматически подключается к Redis
- Просмотр кэша всех сервисов

## 📊 API Документация

После запуска доступны:
- **Auth Service:** http://localhost:8000/docs
- **Profile Service:** http://localhost:8002/docs  
- **Schedule Service:** http://localhost:8001/docs

## 🧪 Тестирование интеграции

### 1. Создание пользователя
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123",
    "first_name": "Test",
    "last_name": "User"
  }'
```

### 2. Получение токена
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123"
  }'
```

### 3. Создание профиля
```bash
curl -X POST "http://localhost:8002/api/v1/profiles/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Test User",
    "bio": "Тестовый пользователь"
  }'
```

## ⚠️ Устранение проблем

### Порты заняты
```bash
# Найти процесс на порту
lsof -i :8000
# Или для Windows
netstat -ano | findstr :8000

# Остановить все контейнеры
docker-compose down
```

### Проблемы с БД
```bash
# Пересоздать базы данных
docker-compose down -v
docker-compose up -d postgres
# Подождать 30 секунд
docker-compose run --rm auth-service alembic upgrade head
```

### Очистка Docker
```bash
# Удалить все остановленные контейнеры
docker system prune -f

# Удалить все неиспользуемые images
docker image prune -a
```

## 🎯 Готово к фронтенду!

После успешного запуска у вас есть:
✅ 3 микросервиса с изолированными БД  
✅ Единая сеть для межсервисного общения  
✅ Готовые API для фронтенда  
✅ Инструменты для мониторинга  

**Следующий шаг:** Создание React/Vue фронтенда! 🚀