"""
Одноразовый скрипт для бэкфилла studios_cache и classrooms_cache в Schedule Service.

Что делает:
    - Читает все Studios и Classrooms из admin БД.
    - Для каждой записи пишет соответствующее '*.created' в event_outbox.
    - Обычный publisher_worker подхватит и опубликует в RabbitMQ.
    - Schedule consumer применит к своим кешам.

Идемпотентность:
    Скрипт безопасно запускать несколько раз. Каждый запуск создаёт новые
    события с новыми event_id. Handler в schedule делает upsert по id с
    проверкой updated_at - повторное событие просто перезапишет данные
    теми же значениями (если они актуальны).

Использование:
    docker compose exec admin-service python scripts/republish_studios_and_classrooms.py
"""

import asyncio
import logging

from sqlalchemy import select

from app.database.connection import AdminAsyncSessionLocal
from app.models.studio import Studio
from app.models.classroom import Classroom
from app.messaging.outbox import (
    record_studio_created,
    record_classroom_created,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("republish")


async def republish_all() -> None:
    """Записать все studios и classrooms в outbox как *.created события."""
    async with AdminAsyncSessionLocal() as session:
        # Студии
        result = await session.execute(select(Studio))
        studios = list(result.scalars().all())
        logger.info("Found %s studios in admin DB", len(studios))
        
        for studio in studios:
            await record_studio_created(session, studio)
        
        # Кабинеты
        result = await session.execute(select(Classroom))
        classrooms = list(result.scalars().all())
        logger.info("Found %s classrooms in admin DB", len(classrooms))
        
        for classroom in classrooms:
            await record_classroom_created(session, classroom)
        
        await session.commit()
        logger.info(
            "Backfill complete: %s studios + %s classrooms recorded in outbox. "
            "Publisher worker will publish them to RabbitMQ within seconds.",
            len(studios), len(classrooms),
        )


if __name__ == "__main__":
    asyncio.run(republish_all())