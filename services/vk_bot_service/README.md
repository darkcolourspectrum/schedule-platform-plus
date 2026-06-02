# VK Bot Service

Микросервис VK-бота сообщества для Schedule Platform Plus. Дополнительный
канал ввода/вывода поверх существующих сервисов платформы - как замена
мобильному приложению.

## Что делает

1. **Приём заявок (лидов).** Пользователь в диалоге с ботом оставляет
   заявку (имя, email, телефон). Бот создаёт лид через публичную ручку
   CRM Service. Доступно всем, в том числе незарегистрированным.

2. **Действия преподавателя.** Распознанный преподаватель видит своё
   расписание на неделю и может отменить занятие прямо из бота. Отмена
   идёт в Schedule Service от имени преподавателя (по его JWT) и публикует
   событие lesson.cancelled - ученики получают уведомление.

3. **Уведомления студентам.** Бот - независимый потребитель событий
   расписания (lesson.created / cancelled / rescheduled). По каждому
   событию он дублирует уведомление в личку VK тем студентам, чей VK
   привязан к аккаунту платформы.

## Принципы

- **Бот не делает VK-авторизацию.** Она целиком на фронте (окно VK ID).
  Бот получает vk_id из Long Poll сообщества (доверенный источник) и по
  нему находит пользователя в своём кеше, наполняемом событиями auth.
  Связь vk_id <-> user_id бот не угадывает - источник истины Auth Service.

- **Изоляция.** Своя БД, свои воркеры, своя очередь RabbitMQ. Не меняет
  поведение notification_service (тот шлёт in-app уведомления параллельно).

- **Надёжность.** Уведомления проходят через очередь outbound_messages:
  событие -> запись в очередь (идемпотентно, в одной транзакции с
  processed_events) -> отправка -> статус (sent/failed/undeliverable).
  Транзиентные сбои повторяет retry-воркер; отказ "не подключил бота"
  (VK 901) помечается undeliverable без повторов.

## Архитектура

```
app/
  api/v1/           health-эндпоинт
  bot/
    dispatcher.py       маршрутизация входящих сообщений в сценарии
    keyboards.py        клавиатуры меню по ролям
    texts.py            тексты сообщений
    context.py          разобранное входящее сообщение
    handlers/           сценарии: lead, schedule, cancel_lesson
    longpoll_worker.py  приём входящих (Bots Long Poll, vkbottle)
  clients/          HTTP-клиенты: auth, crm, schedule; VK API-клиент
  messaging/
    auth_consumer + auth_handlers          users_cache из auth_events
    schedule_consumer + schedule_handlers  VK-уведомления из schedule_events
    outbound_worker.py                     retry исходящих сообщений
  models/           UserCache, DialogState, OutboundMessage,
                    UserToken, ProcessedEvent
  repositories/     слой доступа к данным (Unit of Work)
  services/         user_resolver, token_service, notification_service,
                    notification_sender
  config.py, dependencies.py, main.py
migrations/         Alembic
```

## БД (vk_bot_service_db)

- `users_cache` - read-копия пользователей (user_id <-> vk_id, роль, имя)
- `dialog_states` - состояние FSM диалога по vk_id
- `outbound_messages` - очередь и журнал исходящих VK-сообщений
- `user_tokens` - refresh-токены пользователей (для действий от их имени)
- `processed_events` - идемпотентность consumer'ов

## События RabbitMQ

- Подписка `auth_events` (`user.*`) -> очередь `vk_bot.user_events`
- Подписка `schedule_events` (`lesson.*`) -> очередь `vk_bot.lesson_events`
- Обе с DLX/DLQ. Идемпотентность через processed_events.

## Запуск

См. DEPLOY.md (интеграция в docker-compose, БД, настройка VK сообщества)
и INTEGRATION_NOTES.md (две аддитивные правки auth_service).

Локально:
```bash
pip install -r requirements.txt
cp .env.example .env   # заполнить
alembic upgrade head
python run_server.py
```

Порт: 8006. Health: `/health` и `/api/v1/health`.

## Внешние правки (аддитивные, см. INTEGRATION_NOTES.md)

1. vk_id (Optional) в payload событий user.created / user.updated.
2. internal-роут POST /api/v1/auth/internal/vk-login (X-Internal-API-Key).
