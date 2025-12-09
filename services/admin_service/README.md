# Admin Service - Административная панель и CRM

Enterprise-grade административный сервис для Schedule Platform Plus.

## Что делает этот сервис:

### 1. CRUD Пользователей
- Создание пользователей админом
- Редактирование пользователей
- Блокировка/активация
- Назначение ролей
- Привязка к студиям

### 2. CRUD Студий
- Создание и редактирование студий
- Управление адресами и контактами
- Деактивация студий

### 3. CRUD Кабинетов
- Создание кабинетов в студиях
- Управление характеристиками (вместимость, оборудование)
- Привязка к студиям

### 4. Dashboard (будущее)
- Статистика системы
- Метрики пользователей
- Графики активности

### 5. CRM (будущее)
- Интеграция с соцсетями
- Воронка продаж
- Email/SMS рассылки

## Архитектурные особенности:

### Shared Database Pattern
Вместо HTTP вызовов между сервисами используется:
1. **Redis Cache** - кэширование данных
2. **Read-Only доступ** к Auth Service БД для чтения User данных
3. **Собственная БД** для Studios и Classrooms

### Преимущества:
- ✅ Нет HTTP overhead
- ✅ Данные всегда актуальные
- ✅ Высокая производительность (Redis)
- ✅ Надёжность (нет зависимости от HTTP API)

## Установка:

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Скопируйте .env.example в .env и настройте:
```bash
cp .env.example .env
# Отредактируйте .env
```

3. Примените миграции:
```bash
alembic upgrade head
```

4. Запустите сервис:
```bash
python run_server.py
```

## API Endpoints:

### Users (через User Cache Service)
- GET /api/v1/users - список всех пользователей
- GET /api/v1/users/{id} - пользователь по ID
- GET /api/v1/users/role/{role} - пользователи по роли

### Studios
- GET /api/v1/studios - список студий
- POST /api/v1/studios - создать студию
- GET /api/v1/studios/{id} - студия по ID
- PUT /api/v1/studios/{id} - обновить студию
- DELETE /api/v1/studios/{id} - удалить студию

### Classrooms
- GET /api/v1/studios/{studio_id}/classrooms - кабинеты студии
- POST /api/v1/studios/{studio_id}/classrooms - создать кабинет
- PUT /api/v1/classrooms/{id} - обновить кабинет
- DELETE /api/v1/classrooms/{id} - удалить кабинет

## Безопасность:

- JWT токены от Auth Service
- Internal API Key для межсервисного взаимодействия
- Только админы имеют доступ к endpoints

## Интеграция с другими сервисами:

```
Admin Service
    ├─> Auth Service БД (READ-ONLY) - для User данных
    ├─> Redis - кэширование
    └─> Admin Service БД - Studios, Classrooms
```

Создано: 2025
