"""Сценарии диалога VK-бота."""
from app.bot.handlers.cancel_scenario import CancelLessonScenario
from app.bot.handlers.lead_scenario import LeadScenario
from app.bot.handlers.schedule_scenario import ScheduleScenario

__all__ = [
    "CancelLessonScenario",
    "LeadScenario",
    "ScheduleScenario",
]
