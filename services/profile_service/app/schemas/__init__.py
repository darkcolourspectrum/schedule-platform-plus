"""
Pydantic схемы для Profile Service
"""

# Схемы профилей
from app.schemas.profile import (
    ProfileBase,
    ProfileCreate,
    ProfileUpdate,
    NotificationPreferences,
    ProfileSettings,
    UserInfo,
    ProfileResponse,
    ProfilePublicResponse,
    ProfileSearchResult,
    ProfileListResponse,
    AvatarUploadResponse,
    AvatarInfo,
    StudentInfo,
    TeacherInfo,
    ProfileStatsResponse,
    MessageResponse,
    ErrorResponse,
)

# Общие схемы
from app.schemas.common import (
    SuccessResponse,
    ErrorResponse as CommonErrorResponse,
)

__all__ = [
    # Profile schemas
    "ProfileBase",
    "ProfileCreate",
    "ProfileUpdate",
    "NotificationPreferences",
    "ProfileSettings",
    "UserInfo",
    "ProfileResponse",
    "ProfilePublicResponse",
    "ProfileSearchResult",
    "ProfileListResponse",
    "AvatarUploadResponse",
    "AvatarInfo",
    "StudentInfo",
    "TeacherInfo",
    "ProfileStatsResponse",
    "MessageResponse",
    "ErrorResponse",

    # Common schemas
    "SuccessResponse",
    "CommonErrorResponse",
]