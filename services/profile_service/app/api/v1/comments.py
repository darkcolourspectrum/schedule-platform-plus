"""
API endpoints для работы с комментариями и отзывами
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query, Path, Request

from app.dependencies import (
    CurrentUser, OptionalCurrentUser, CurrentAdmin,
    CommentServiceDep, PaginationParams, verify_comment_access
)
from app.schemas.comment import (
    CommentCreate, CommentUpdate, CommentResponse, CommentListResponse,
    ReviewCreate, TeacherReviewsResponse, AdminNoteCreate,
    CommentModerationRequest, LessonCommentCreate, UserCommentsResponse
)
from app.schemas.common import SuccessResponse
from app.models.comment import CommentType, CommentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.post(
    "/",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание комментария",
    description="Создание нового комментария"
)
async def create_comment(
    comment_data: CommentCreate,
    request: Request,
    current_user: CurrentUser = ...,
    comment_service: CommentServiceDep = ...
):
    """Создание нового комментария"""
    try:
        author_id = current_user["id"]
        
        # Получаем IP и User-Agent для логирования
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Создаем комментарий
        comment = await comment_service.create_comment(
            author_id=author_id,
            target_type=comment_data.target_type,
            target_id=comment_data.target_id,
            comment_type=comment_data.comment_type,
            content=comment_data.content,
            title=comment_data.title,
            rating=comment_data.rating,
            is_anonymous=comment_data.is_anonymous,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create comment"
            )
        
        logger.info(f"Создан комментарий {comment['id']} пользователем {author_id}")
        return CommentResponse(**comment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка создания комментария: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{target_type}/{target_id}",
    response_model=CommentListResponse,
    summary="Получение комментариев",
    description="Получение комментариев для объекта"
)
async def get_comments_for_target(
    target_type: str = Path(..., description="Тип объекта (teacher, student, lesson, profile)"),
    target_id: int = Path(..., description="ID объекта"),
    comment_type: Optional[CommentType] = Query(None, description="Тип комментария"),
    pagination: PaginationParams = ...,
    current_user: OptionalCurrentUser = ...,
    comment_service: CommentServiceDep = ...
):
    """Получение комментариев для объекта"""
    try:
        viewer_user_id = current_user["id"] if current_user else None
        
        # Получаем комментарии
        comments = await comment_service.get_comments_for_target(
            target_type=target_type,
            target_id=target_id,
            comment_type=comment_type,
            viewer_user_id=viewer_user_id,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
        # Подсчитываем общее количество
        total = len(comments)
        has_more = len(comments) == pagination["limit"]
        
        return CommentListResponse(
            comments=[CommentResponse(**comment) for comment in comments],
            total=total,
            limit=pagination["limit"],
            offset=pagination["offset"],
            has_more=has_more
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения комментариев для {target_type}:{target_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put(
    "/{comment_id}",
    response_model=CommentResponse,
    summary="Обновление комментария",
    description="Обновление существующего комментария"
)
async def update_comment(
    comment_id: int = Path(..., description="ID комментария"),
    comment_data: CommentUpdate = ...,
    current_user: CurrentUser = ...,
    comment_service: CommentServiceDep = ...
):
    """Обновление комментария"""
    try:
        author_id = current_user["id"]
        
        # Обновляем комментарий
        updated_comment = await comment_service.update_comment(
            comment_id=comment_id,
            author_id=author_id,
            content=comment_data.content,
            title=comment_data.title,
            rating=comment_data.rating,
            edit_reason=comment_data.edit_reason
        )
        
        if not updated_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found or cannot be edited"
            )
        
        logger.info(f"Обновлен комментарий {comment_id} пользователем {author_id}")
        return CommentResponse(**updated_comment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления комментария {comment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/reviews/teachers/{teacher_id}",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание отзыва о преподавателе",
    description="Создание публичного отзыва о преподавателе"
)
async def create_teacher_review(
    teacher_id: int = Path(..., description="ID преподавателя"),
    review_data: ReviewCreate = ...,
    request: Request = ...,
    current_user: CurrentUser = ...,
    comment_service: CommentServiceDep = ...
):
    """Создание отзыва о преподавателе"""
    try:
        author_id = current_user["id"]
        
        # Проверяем, что пользователь не оставляет отзыв сам себе
        if author_id == teacher_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot leave a review for yourself"
            )
        
        # Получаем IP и User-Agent
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Создаем отзыв
        review = await comment_service.create_comment(
            author_id=author_id,
            target_type="teacher",
            target_id=teacher_id,
            comment_type=CommentType.PUBLIC_REVIEW,
            content=review_data.content,
            title=review_data.title,
            rating=review_data.rating,
            is_anonymous=review_data.is_anonymous,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if not review:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create review"
            )
        
        logger.info(f"Создан отзыв о преподавателе {teacher_id} от пользователя {author_id}")
        return CommentResponse(**review)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка создания отзыва о преподавателе {teacher_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/reviews/teachers/{teacher_id}",
    response_model=TeacherReviewsResponse,
    summary="Отзывы о преподавателе",
    description="Получение отзывов о преподавателе со статистикой"
)
async def get_teacher_reviews(
    teacher_id: int = Path(..., description="ID преподавателя"),
    pagination: PaginationParams = ...,
    comment_service: CommentServiceDep = ...
):
    """Получение отзывов о преподавателе"""
    try:
        reviews_data = await comment_service.get_teacher_reviews(
            teacher_id=teacher_id,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
        return TeacherReviewsResponse(**reviews_data)
        
    except Exception as e:
        logger.error(f"Ошибка получения отзывов о преподавателе {teacher_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/admin-notes",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание административной заметки",
    description="Создание приватной заметки администратора"
)
async def create_admin_note(
    note_data: AdminNoteCreate,
    request: Request,
    current_user: CurrentAdmin = ...,
    comment_service: CommentServiceDep = ...
):
    """Создание административной заметки"""
    try:
        author_id = current_user["id"]
        
        # Получаем IP и User-Agent
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Создаем заметку
        note = await comment_service.create_comment(
            author_id=author_id,
            target_type=note_data.target_type,
            target_id=note_data.target_id,
            comment_type=CommentType.ADMIN_NOTE,
            content=note_data.content,
            title=note_data.title,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if not note:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create admin note"
            )
        
        logger.info(f"Создана админ заметка {note['id']} пользователем {author_id}")
        return CommentResponse(**note)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка создания административной заметки: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{comment_id}/moderate",
    response_model=CommentResponse,
    summary="Модерация комментария",
    description="Модерация комментария администратором"
)
async def moderate_comment(
    comment_id: int = Path(..., description="ID комментария"),
    moderation_data: CommentModerationRequest = ...,
    current_user: CurrentAdmin = ...,
    comment_service: CommentServiceDep = ...
):
    """Модерация комментария"""
    try:
        moderator_id = current_user["id"]
        
        # Выполняем модерацию
        moderated_comment = await comment_service.moderate_comment(
            comment_id=comment_id,
            moderator_id=moderator_id,
            action=moderation_data.action,
            reason=moderation_data.reason
        )
        
        if not moderated_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        logger.info(f"Модерация комментария {comment_id}: {moderation_data.action} модератором {moderator_id}")
        return CommentResponse(**moderated_comment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка модерации комментария {comment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/users/{user_id}",
    response_model=UserCommentsResponse,
    summary="Комментарии пользователя",
    description="Получение комментариев пользователя"
)
async def get_user_comments(
    user_id: int = Path(..., description="ID пользователя"),
    pagination: PaginationParams = ...,
    current_user: CurrentUser = ...,
    comment_service: CommentServiceDep = ...
):
    """Получение комментариев пользователя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own comments"
            )
        
        # Получаем комментарии пользователя
        comments = await comment_service.get_user_comments(
            user_id=user_id,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
        return UserCommentsResponse(
            comments=comments,
            total=len(comments),
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения комментариев пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/lessons/{lesson_id}",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Комментарий к уроку",
    description="Создание комментария к уроку"
)
async def create_lesson_comment(
    lesson_id: int = Path(..., description="ID урока"),
    comment_data: LessonCommentCreate = ...,
    request: Request = ...,
    current_user: CurrentUser = ...,
    comment_service: CommentServiceDep = ...
):
    """Создание комментария к уроку"""
    try:
        author_id = current_user["id"]
        
        # Получаем IP и User-Agent
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Создаем комментарий к уроку
        comment = await comment_service.create_comment(
            author_id=author_id,
            target_type="lesson",
            target_id=lesson_id,
            comment_type=CommentType.LESSON_COMMENT,
            content=comment_data.content,
            title=comment_data.title,
            rating=comment_data.rating,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create lesson comment"
            )
        
        logger.info(f"Создан комментарий к уроку {lesson_id} от пользователя {author_id}")
        return CommentResponse(**comment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка создания комментария к уроку {lesson_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )