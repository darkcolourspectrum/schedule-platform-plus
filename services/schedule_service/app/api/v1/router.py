"""
API v1 Router
"""

from fastapi import APIRouter

from app.api.v1 import recurring_patterns, lessons, schedule, health

api_router = APIRouter(prefix="/api/v1")

# Include routers
api_router.include_router(health.router)
api_router.include_router(recurring_patterns.router)
api_router.include_router(lessons.router)
api_router.include_router(schedule.router)
