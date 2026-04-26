"""
Публикация событий Schedule Service в RabbitMQ.

Глобальный экземпляр publisher создаётся при старте приложения (через lifespan)
и переиспользуется во всех handler-ах. Не создавай новый экземпляр на каждый
вызов — соединение медленное.
"""

import logging
from typing import List, Optional
from datetime import date, time

from shared.messaging import EventPublisher
from app.config import settings

logger = logging.getLogger(__name__)


publisher = EventPublisher(amqp_url=settings.rabbitmq_url)


async def publish_lesson_created(
    lesson_id: int,
    teacher_id: int,
    student_ids: List[int],
    studio_id: int,
    classroom_id: Optional[int],
    lesson_date: date,
    start_time: time,
    end_time: time,
) -> None:
    """Опубликовать событие создания занятия."""
    try:
        await publisher.publish(
            routing_key="lesson.created",
            payload={
                "event_type": "lesson.created",
                "lesson_id": lesson_id,
                "teacher_id": teacher_id,
                "student_ids": student_ids,
                "studio_id": studio_id,
                "classroom_id": classroom_id,
                "lesson_date": lesson_date.isoformat(),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to publish lesson.created event: lesson_id=%s error=%s",
            lesson_id, exc,
        )