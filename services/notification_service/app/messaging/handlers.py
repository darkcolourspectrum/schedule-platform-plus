"""
Обработчики событий из RabbitMQ.

Каждый handler знает как преобразовать событие конкретного типа
в одно или несколько уведомлений.
"""

import logging
from typing import Dict, Any
from datetime import datetime

from app.database.connection import AsyncSessionLocal
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def handle_lesson_created(event: Dict[str, Any]) -> None:
    """
    Обработать событие создания занятия.
    Создаёт уведомления для всех учеников этого занятия.
    """
    lesson_id = event["lesson_id"]
    student_ids = event.get("student_ids", [])
    teacher_id = event["teacher_id"]
    studio_id = event["studio_id"]
    lesson_date = event["lesson_date"]
    start_time = event["start_time"]
    
    if not student_ids:
        logger.info("lesson.created event has no students, skipping: lesson_id=%s", lesson_id)
        return
    
    title = "Новое занятие"
    message = f"Преподаватель назначил вам занятие {lesson_date} в {start_time[:5]}"
    
    payload = {
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "studio_id": studio_id,
        "lesson_date": lesson_date,
        "start_time": start_time,
    }
    
    async with AsyncSessionLocal() as db:
        service = NotificationService(db)
        for student_id in student_ids:
            await service.create_notification(
                user_id=student_id,
                type="lesson_created",
                title=title,
                message=message,
                payload=payload,
            )
        logger.info(
            "Created %d notifications for lesson_id=%s",
            len(student_ids), lesson_id,
        )