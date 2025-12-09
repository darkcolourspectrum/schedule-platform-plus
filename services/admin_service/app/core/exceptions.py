"""Custom Exceptions"""
from fastapi import HTTPException, status

class AdminServiceException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)

class StudioNotFoundException(AdminServiceException):
    def __init__(self, studio_id: int):
        super().__init__(f"Studio {studio_id} not found", status.HTTP_404_NOT_FOUND)

class ClassroomNotFoundException(AdminServiceException):
    def __init__(self, classroom_id: int):
        super().__init__(f"Classroom {classroom_id} not found", status.HTTP_404_NOT_FOUND)

class UserNotFoundException(AdminServiceException):
    def __init__(self, user_id: int):
        super().__init__(f"User {user_id} not found", status.HTTP_404_NOT_FOUND)

class PermissionDeniedException(AdminServiceException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)

class InvalidTokenException(AdminServiceException):
    def __init__(self):
        super().__init__("Invalid or expired token", status.HTTP_401_UNAUTHORIZED)
