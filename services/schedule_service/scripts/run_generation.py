"""
Ручной запуск одного такта генерации расписания.

Запуск:
    docker compose exec schedule-service python scripts/run_generation.py

Делает ровно то же, что фоновый воркер делает по таймеру: проходит по
активным шаблонам и догенерирует занятия до конца горизонта.

Зачем нужен отдельно от воркера:
    - проверить работу генерации, не дожидаясь следующего такта;
    - разово продлить расписание после массовой правки шаблонов;
    - убедиться, что воркер вообще способен отработать, если в логах
      подозрительно тихо.

Безопасен для повторных запусков: генерация идемпотентна, второй запуск
подряд создаст ноль занятий.
"""

import asyncio
import logging

from app.database.connection import ScheduleAsyncSessionLocal
from app.domain.recurrence import generation_horizon_end, today_in_studio_tz
from app.services.generation_worker import ScheduleGenerationWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("run_generation")


async def main() -> None:
    today = today_in_studio_tz()
    horizon = generation_horizon_end(today)

    print()
    print(f"Сегодня в часовом поясе студии: {today}")
    print(f"Горизонт генерации до:          {horizon}")
    print()

    generation_worker = ScheduleGenerationWorker(
        session_factory=ScheduleAsyncSessionLocal
    )

    processed, created = await generation_worker.run_once()

    print()
    print(f"Обработано шаблонов: {processed}")
    print(f"Создано занятий:     {created}")
    print()

    if processed == 0 and created == 0:
        print(
            "Ноль обработанных шаблонов означает одно из двух: активных "
            "шаблонов нет, либо блокировку держит фоновый воркер. "
            "Второе - нормально, повтори через минуту."
        )
        print()


if __name__ == "__main__":
    asyncio.run(main())
