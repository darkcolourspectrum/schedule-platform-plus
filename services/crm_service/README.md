# CRM Service - Воронка лидов

Микросервис CRM-воронки лидов для Schedule Platform Plus.

## Что делает этот сервис

CRM закрывает пробел жизненного цикла клиента: до этого `User` появлялся
только через самостоятельную регистрацию. CRM добавляет путь
"заявка с рекламы -> обработка -> первое занятие -> аккаунт".

### Воронка лидов
- Приём заявок через публичную ручку (форма на лендинге)
- Канбан для работы админа с лидом
- Доведение лида до записи на первое занятие
- Конвертация лида в provisioned-юзера (обычный `User` без пароля)

### Статусы воронки
`new -> contacted -> trial_scheduled -> trial_attended -> converted`
плюс `lost` (терминальный, достижим с любого этапа, с указанием причины).

## Архитектурные принципы

- **Лид и клиент - разные записи.** Лид живёт в crm-service, клиент (`User`)
  в auth-service. Конвертация не превращает лид в юзера, а создаёт нового
  юзера и проставляет в лиде ссылку (`converted_user_id`).
- **Понятие "лид" не протекает за пределы crm-service.** Schedule,
  notification, profile работают только с `User`.
- **Единственная межсервисная HTTP-связь:** CRM -> auth (создание
  provisioned-юзера). CRM про расписание не знает - занятие создаёт фронт
  обычным вызовом к schedule-service.
- Те же паттерны, что в остальных сервисах: FastAPI, SQLAlchemy 2 async,
  Alembic, outbox для своих событий, consumer для чужих, DLX/DLQ,
  идемпотентность через `processed_events`.

## Архитектура

### База данных (`crm_service_db`)
- `leads` - потенциальные клиенты
- `lead_activities` - журнал истории по лиду (заметки, звонки, смены статуса)
- `users_cache` - read-копия пользователей из `auth_events` (кто `assigned_to`)
- `processed_events` - идемпотентность consumer'а
- `event_outbox` - публикация своих событий

### События RabbitMQ
- exchange `crm_events` (publisher): `lead.created`, `lead.status_changed`,
  `lead.converted`
- подписка на `auth_events` (`user.*`, `role.*`) - для `users_cache`

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Скопируйте `.env.example` в `.env` и настройте:
```bash
cp .env.example .env
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

### Публичный (без авторизации)
- `POST /api/crm/leads/public` - приём заявки с лендинга

### Защищённые (роль admin)
- `GET /api/crm/leads` - список лидов с фильтрами
- `GET /api/crm/leads/{id}` - карточка лида + лента активностей
- `PATCH /api/crm/leads/{id}` - смена статуса / assigned_to / notes
- `POST /api/crm/leads/{id}/activities` - добавить заметку
- `POST /api/crm/leads/{id}/convert-to-user` - создать provisioned-юзера
- `POST /api/crm/leads/{id}/finalize` - финальная конвертация

## Безопасность

- JWT токены от Auth Service (валидация через `shared/auth_lib`)
- Internal API Key для межсервисного взаимодействия (CRM -> auth)
- Защищённые endpoints доступны только админам

## Порт

8005

Создано: 2026