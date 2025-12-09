"""
Репозитории для Profile Service
"""
from app.repositories.base import BaseRepository
from app.repositories.profile_repository import ProfileRepository

__all__ = [
    "BaseRepository",
    "ProfileRepository",
]