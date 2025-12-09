"""
Models package for Admin Service
"""

from app.models.base import Base, TimestampMixin
from app.models.studio import Studio
from app.models.classroom import Classroom
from app.models.auth_models import User, Role

__all__ = [
    "Base",
    "TimestampMixin",
    "Studio",
    "Classroom",
    "User",  # READ-ONLY from Auth Service
    "Role",  # READ-ONLY from Auth Service
]
