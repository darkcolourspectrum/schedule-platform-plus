"""Dashboard schemas"""
from typing import List, Dict, Any
from pydantic import BaseModel


class UserStats(BaseModel):
    """Статистика пользователей"""
    total: int
    active: int
    students: int
    teachers: int


class StudioStats(BaseModel):
    """Статистика студий"""
    total: int
    active: int


class ClassroomStats(BaseModel):
    """Статистика кабинетов"""
    total: int
    active: int


class SystemStatsResponse(BaseModel):
    """Системная статистика"""
    users: UserStats
    studios: StudioStats
    classrooms: ClassroomStats


class QuickAction(BaseModel):
    """Быстрое действие"""
    id: str
    title: str
    url: str


class AdminDashboardResponse(BaseModel):
    """Дашборд администратора"""
    user_id: int
    system_stats: SystemStatsResponse
    quick_actions: List[QuickAction]
