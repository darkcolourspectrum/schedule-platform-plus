"""Notification API endpoints"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user, get_notification_service
from app.services.notification_service import NotificationService
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = False,
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Получить список уведомлений текущего пользователя."""
    user_id = current_user["user_id"]
    return await service.get_user_notifications(
        user_id=user_id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Получить количество непрочитанных уведомлений (для badge)."""
    user_id = current_user["user_id"]
    count = await service.get_unread_count(user_id)
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_as_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Пометить уведомление как прочитанное."""
    user_id = current_user["user_id"]
    success = await service.mark_as_read(notification_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or already read",
        )
    return MarkReadResponse(success=True, message="Notification marked as read")


@router.post("/read-all", response_model=MarkReadResponse)
async def mark_all_as_read(
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Пометить все уведомления пользователя как прочитанные."""
    user_id = current_user["user_id"]
    count = await service.mark_all_as_read(user_id)
    return MarkReadResponse(success=True, message=f"{count} notifications marked as read")


@router.post(
    "",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification_dev(
    data: NotificationCreate,
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """
    DEV-only endpoint для ручного создания уведомлений.
    В production уведомления будут создаваться только из RabbitMQ-консьюмера.
    """
    notification = await service.create_notification(
        user_id=data.user_id,
        type=data.type,
        title=data.title,
        message=data.message,
        payload=data.payload,
    )
    return notification