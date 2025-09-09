"""
Репозитории для Profile Service
"""

from app.repositories.base import BaseRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.comment_repository import CommentRepository
from app.repositories.activity_repository import ActivityRepository

__all__ = [
    "BaseRepository",
    "ProfileRepository", 
    "CommentRepository",
    "ActivityRepository"
]