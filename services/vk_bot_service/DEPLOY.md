# Развёртывание vk_bot_service

Сервис изолирован: своя БД, свои воркеры. Чтобы поднять его в общем
стеке, нужно три аддитивных вставки в инфраструктуру проекта (ничего
существующего не меняется) и две правки в auth_service (см.
INTEGRATION_NOTES.md).

## 1. Папка сервиса

Положить каталог `vk_bot_service/` в `services/` рядом с остальными:
`schedule-platform-plus/services/vk_bot_service/`.

## 2. БД и пользователь (docker/init-databases.sql)

Добавить в конец файла (по образцу остальных сервисов):

```sql
-- VK Bot Service Database
CREATE USER vk_bot_user WITH PASSWORD 'vk_bot_password';
CREATE DATABASE vk_bot_service_db OWNER vk_bot_user;
GRANT ALL PRIVILEGES ON DATABASE vk_bot_service_db TO vk_bot_user;

\connect vk_bot_service_db;
GRANT ALL ON SCHEMA public TO vk_bot_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO vk_bot_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO vk_bot_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO vk_bot_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO vk_bot_user;
\connect postgres;
```

Примечание: init-databases.sql выполняется только при ПЕРВОЙ инициализации
тома postgres_data. Если БД уже инициализирована, создать БД и пользователя
вручную (psql) теми же командами.

## 3. Сервис в docker-compose.yml

Добавить в раздел services (по образцу crm-service):

```yaml
  # VK BOT SERVICE
  vk-bot-service:
    build:
      context: .
      dockerfile: services/vk_bot_service/Dockerfile
    container_name: vk_bot_service
    restart: unless-stopped
    volumes:
      - ./services/vk_bot_service/migrations:/app/migrations
    environment:
      APP_NAME: VK Bot Service
      APP_VERSION: 1.0.0
      DEBUG: ${DEBUG:-true}
      ENVIRONMENT: ${ENVIRONMENT:-development}
      HOST: 0.0.0.0
      PORT: 8006
      DATABASE_URL: postgresql+asyncpg://vk_bot_user:vk_bot_password@postgres:5432/vk_bot_service_db
      JWT_BLACKLIST_REDIS_URL: redis://redis:6379/15
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      JWT_ALGORITHM: ${JWT_ALGORITHM:-HS256}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
      AUTH_SERVICE_URL: http://auth-service:8000
      CRM_SERVICE_URL: http://crm-service:8005
      SCHEDULE_SERVICE_URL: http://schedule-service:8001
      CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://localhost
      CORS_ALLOW_CREDENTIALS: "true"
      RABBITMQ_URL: ${RABBITMQ_URL}
      VK_GROUP_TOKEN: ${VK_GROUP_TOKEN:-}
      VK_GROUP_ID: ${VK_GROUP_ID:-0}
    ports:
      - "8006:8006"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    command: >
      sh -c "
        echo 'Applying VK Bot Service migrations...' &&
        alembic upgrade head &&
        echo 'Migrations applied, starting VK Bot Service...' &&
        python run_server.py
      "
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8006/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - schedule_platform_network
```

## 4. Корневой .env

Добавить токен сообщества и group_id:

```env
VK_GROUP_TOKEN=vk1.a.xxxxx
VK_GROUP_ID=123456789
```

Без них сервис поднимется, но Long Poll не запустится (бот не будет
принимать входящие). Уведомления студентам в очередь будут ставиться,
но отправка будет откладываться до настройки VK.

## 5. Правки auth_service (см. INTEGRATION_NOTES.md)

- ПРАВКА #1: добавить vk_id (Optional) в payload событий user.created /
  user.updated. Нужно, чтобы бот знал vk_id студентов для доставки.
- ПРАВКА #2: добавить internal-роут POST /api/v1/auth/internal/vk-login
  (X-Internal-API-Key, body {vk_id}) поверх готового auth_service.vk_login.
  Нужно для действий преподавателя (расписание/отмена) от его имени.

Обе правки строго аддитивные, согласуются отдельным шагом.

## 6. Настройка VK сообщества

- Создать сообщество VK (если ещё нет).
- Управление -> Работа с API -> Ключи доступа: создать ключ с правами на
  сообщения. Это VK_GROUP_TOKEN.
- Работа с API -> Long Poll API: включить, выбрать последнюю версию API,
  в типах событий включить "Входящие сообщения" (message_new).
- Сообщения -> Настройки -> разрешить сообщения сообществу.
- group_id (числовой) - в адресе сообщества или через API. Это VK_GROUP_ID.
