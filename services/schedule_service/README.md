# Schedule Service - Сервис расписания

Микросервис для управления расписанием занятий в Schedule Platform Plus.

## Основные возможности

### Управление занятиями
- ✅ Создание разовых занятий
- ✅ Создание повторяющихся занятий (recurring patterns)
- ✅ Автоматическая генерация занятий из шаблонов
- ✅ Отмена и изменение статусов занятий
- ✅ Проверка конфликтов кабинетов

### Просмотр расписания
- ✅ Расписание студии (все преподаватели)
- ✅ Расписание преподавателя
- ✅ Расписание ученика (только свои занятия)
- ✅ Фильтрация по дате и времени

### Статусы занятий
- `scheduled` - запланировано
- `completed` - завершено
- `cancelled` - отменено
- `missed` - пропущено

## Архитектура

### База данных
Собственная БД для Schedule Service с таблицами:
- `recurring_patterns` - шаблоны повторяющихся занятий
- `lessons` - конкретные занятия
- `lesson_students` - связь занятий с учениками

### Интеграция с другими сервисами
- **Auth Service БД (READ-ONLY)** - для чтения данных пользователей
- **Admin Service API** - для получения информации о студиях и кабинетах
- **Redis** - кэширование расписаний

### Генерация занятий
Система автоматически генерирует конкретные занятия из recurring patterns:
- При создании шаблона → генерация на 2 недели вперед
- Ежедневный cron job (00:00) → догенерация недостающих занятий
- При запросе расписания → проверка и догенерация при необходимости

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Настройте окружение:
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

## API Endpoints

### Recurring Patterns (Шаблоны)
- `POST /api/v1/schedule/recurring-patterns` - создать шаблон
- `GET /api/v1/schedule/recurring-patterns` - список шаблонов
- `GET /api/v1/schedule/recurring-patterns/{id}` - получить шаблон
- `PATCH /api/v1/schedule/recurring-patterns/{id}` - обновить шаблон
- `DELETE /api/v1/schedule/recurring-patterns/{id}` - удалить шаблон

### Lessons (Занятия)
- `POST /api/v1/schedule/lessons` - создать разовое занятие
- `GET /api/v1/schedule/lessons/{id}` - получить занятие
- `PATCH /api/v1/schedule/lessons/{id}` - обновить занятие
- `DELETE /api/v1/schedule/lessons/{id}` - удалить занятие

### Schedule (Расписание)
- `GET /api/v1/schedule/studios/{studio_id}` - расписание студии
- `GET /api/v1/schedule/teachers/{teacher_id}` - расписание преподавателя
- `GET /api/v1/schedule/students/{student_id}` - занятия ученика

### Utilities
- `POST /api/v1/schedule/generate` - ручная генерация занятий
- `GET /api/v1/schedule/conflicts` - проверка конфликтов

## Безопасность

- JWT токены от Auth Service
- Проверка ролей (admin, teacher, student)
- Internal API Key для межсервисного взаимодействия

## Часовой пояс

По умолчанию используется `Asia/Tomsk`.
Все время хранится в БД и обрабатывается в этом часовом поясе.

## Разработка

### Структура проекта
```
schedule_service/
├── app/
│   ├── api/v1/          # API endpoints
│   ├── models/          # SQLAlchemy модели
│   ├── schemas/         # Pydantic схемы
│   ├── services/        # Бизнес-логика
│   ├── repositories/    # Работа с БД
│   ├── database/        # Подключения к БД
│   ├── core/            # Безопасность, исключения
│   └── config.py        # Конфигурация
├── migrations/          # Alembic миграции
└── run_server.py        # Точка входа
```

Создано: 2025
