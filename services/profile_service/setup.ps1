# Команды для ручного создания структуры в PowerShell
# Копируйте и вставляйте по частям если скрипт не работает

# Создание основных папок
New-Item -ItemType Directory -Path "app" -Force
New-Item -ItemType Directory -Path "app/api" -Force
New-Item -ItemType Directory -Path "app/api/v1" -Force
New-Item -ItemType Directory -Path "app/core" -Force
New-Item -ItemType Directory -Path "app/database" -Force
New-Item -ItemType Directory -Path "app/models" -Force
New-Item -ItemType Directory -Path "app/repositories" -Force
New-Item -ItemType Directory -Path "app/services" -Force
New-Item -ItemType Directory -Path "app/schemas" -Force
New-Item -ItemType Directory -Path "app/utils" -Force
New-Item -ItemType Directory -Path "migrations" -Force
New-Item -ItemType Directory -Path "migrations/versions" -Force
New-Item -ItemType Directory -Path "scripts" -Force
New-Item -ItemType Directory -Path "tests" -Force
New-Item -ItemType Directory -Path "tests/api" -Force
New-Item -ItemType Directory -Path "tests/services" -Force
New-Item -ItemType Directory -Path "static" -Force
New-Item -ItemType Directory -Path "static/avatars" -Force

# Создание основных файлов app/
New-Item -ItemType File -Path "app/__init__.py" -Force
New-Item -ItemType File -Path "app/main.py" -Force
New-Item -ItemType File -Path "app/config.py" -Force
New-Item -ItemType File -Path "app/dependencies.py" -Force

# Создание API файлов
New-Item -ItemType File -Path "app/api/__init__.py" -Force
New-Item -ItemType File -Path "app/api/router.py" -Force
New-Item -ItemType File -Path "app/api/v1/__init__.py" -Force
New-Item -ItemType File -Path "app/api/v1/profiles.py" -Force
New-Item -ItemType File -Path "app/api/v1/comments.py" -Force
New-Item -ItemType File -Path "app/api/v1/dashboard.py" -Force
New-Item -ItemType File -Path "app/api/v1/avatars.py" -Force

# Создание core файлов
New-Item -ItemType File -Path "app/core/__init__.py" -Force
New-Item -ItemType File -Path "app/core/exceptions.py" -Force
New-Item -ItemType File -Path "app/core/middleware.py" -Force

# Создание database файлов
New-Item -ItemType File -Path "app/database/__init__.py" -Force
New-Item -ItemType File -Path "app/database/connection.py" -Force
New-Item -ItemType File -Path "app/database/redis_client.py" -Force

# Создание models файлов
New-Item -ItemType File -Path "app/models/__init__.py" -Force
New-Item -ItemType File -Path "app/models/base.py" -Force
New-Item -ItemType File -Path "app/models/profile.py" -Force
New-Item -ItemType File -Path "app/models/comment.py" -Force
New-Item -ItemType File -Path "app/models/activity.py" -Force

# Создание repositories файлов
New-Item -ItemType File -Path "app/repositories/__init__.py" -Force
New-Item -ItemType File -Path "app/repositories/base.py" -Force
New-Item -ItemType File -Path "app/repositories/profile_repository.py" -Force
New-Item -ItemType File -Path "app/repositories/comment_repository.py" -Force

# Создание services файлов
New-Item -ItemType File -Path "app/services/__init__.py" -Force
New-Item -ItemType File -Path "app/services/auth_integration.py" -Force
New-Item -ItemType File -Path "app/services/schedule_integration.py" -Force
New-Item -ItemType File -Path "app/services/profile_service.py" -Force
New-Item -ItemType File -Path "app/services/comment_service.py" -Force
New-Item -ItemType File -Path "app/services/dashboard_service.py" -Force
New-Item -ItemType File -Path "app/services/redis_cache_service.py" -Force
New-Item -ItemType File -Path "app/services/avatar_service.py" -Force

# Создание schemas файлов
New-Item -ItemType File -Path "app/schemas/__init__.py" -Force
New-Item -ItemType File -Path "app/schemas/profile.py" -Force
New-Item -ItemType File -Path "app/schemas/comment.py" -Force
New-Item -ItemType File -Path "app/schemas/dashboard.py" -Force
New-Item -ItemType File -Path "app/schemas/common.py" -Force

# Создание utils файлов
New-Item -ItemType File -Path "app/utils/__init__.py" -Force
New-Item -ItemType File -Path "app/utils/image_processing.py" -Force
New-Item -ItemType File -Path "app/utils/cache_keys.py" -Force

# Создание конфигурационных файлов
New-Item -ItemType File -Path ".env.example" -Force
New-Item -ItemType File -Path "run_server.py" -Force
New-Item -ItemType File -Path "alembic.ini" -Force
New-Item -ItemType File -Path "README.md" -Force

# Создание файлов миграций
New-Item -ItemType File -Path "migrations/env.py" -Force
New-Item -ItemType File -Path "migrations/script.py.mako" -Force

# Создание скриптов
New-Item -ItemType File -Path "scripts/init_database.py" -Force
New-Item -ItemType File -Path "scripts/check_connections.py" -Force

# Создание тестовых файлов
New-Item -ItemType File -Path "tests/__init__.py" -Force
New-Item -ItemType File -Path "tests/conftest.py" -Force
New-Item -ItemType File -Path "tests/api/__init__.py" -Force
New-Item -ItemType File -Path "tests/api/test_profiles.py" -Force
New-Item -ItemType File -Path "tests/api/test_dashboard.py" -Force
New-Item -ItemType File -Path "tests/services/__init__.py" -Force
New-Item -ItemType File -Path "tests/services/test_profile_service.py" -Force

Write-Host "Структура создана!" -ForegroundColor Green