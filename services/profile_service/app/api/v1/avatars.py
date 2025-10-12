"""
API endpoints для работы с аватарами пользователей
"""

import logging
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Path
from fastapi.responses import FileResponse
import os

from app.dependencies import CurrentUser, ProfileServiceDep, extract_role_name
from app.services.avatar_service import avatar_service
from app.schemas.profile import AvatarUploadResponse, AvatarInfo
from app.schemas.common import SuccessResponse
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/avatars", tags=["Avatars"])


@router.post(
    "/{user_id}",
    response_model=AvatarUploadResponse,
    summary="Загрузка аватара",
    description="Загрузка и обработка аватара пользователя"
)
async def upload_avatar(
    user_id: int = Path(..., description="ID пользователя"),
    file: UploadFile = File(..., description="Файл изображения"),
    current_user: CurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Загрузка аватара пользователя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = extract_role_name(current_user.get("role"))
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only upload avatar for your own profile"
            )
        
        # Проверяем существование профиля
        profile = await profile_service.get_profile_by_user_id(user_id)
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        # Загружаем аватар
        upload_result = await avatar_service.upload_avatar(user_id, file)
        
        if not upload_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=upload_result["error"]
            )
        
        # Обновляем профиль с новым аватаром
        await profile_service.update_avatar(user_id, upload_result["filename"])
        
        logger.info(f"Загружен аватар для пользователя {user_id}: {upload_result['filename']}")
        
        return AvatarUploadResponse(
            success=True,
            filename=upload_result["filename"],
            url=upload_result["url"],
            size=upload_result["size"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка загрузки аватара для пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Avatar upload failed"
        )


@router.get(
    "/{user_id}/info",
    response_model=AvatarInfo,
    summary="Информация об аватаре",
    description="Получение информации об аватаре пользователя"
)
async def get_avatar_info(
    user_id: int = Path(..., description="ID пользователя"),
    profile_service: ProfileServiceDep = ...
):
    """Получение информации об аватаре"""
    try:
        # Получаем профиль для получения имени файла аватара
        profile = await profile_service.get_profile_by_user_id(user_id)
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        avatar_filename = profile.get("avatar_filename")
        if not avatar_filename:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User has no avatar"
            )
        
        # Получаем информацию об аватаре
        avatar_info = await avatar_service.get_avatar_info(avatar_filename)
        if not avatar_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Avatar file not found"
            )
        
        return AvatarInfo(**avatar_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения информации об аватаре пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get(
    "/files/{filename}",
    summary="Получение файла аватара",
    description="Отдача файла аватара пользователя",
    response_class=FileResponse
)
async def get_avatar_file(
    filename: str = Path(..., description="Имя файла аватара")
):
    """Получение файла аватара"""
    try:
        from fastapi.responses import FileResponse
        import os
        from app.config import settings
        
        # Проверяем безопасность имени файла (защита от path traversal)
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename"
            )
        
        # Проверяем что файл начинается с user_
        if not filename.startswith('user_'):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Avatar not found"
            )
        
        filepath = os.path.join(settings.avatar_upload_full_path, filename)
        
        if not os.path.exists(filepath):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Avatar file not found"
            )
        
        # Определяем MIME тип
        if filename.endswith('.png'):
            media_type = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            media_type = 'image/jpeg'
        elif filename.endswith('.webp'):
            media_type = 'image/webp'
        else:
            media_type = 'application/octet-stream'
        
        return FileResponse(
            path=filepath,
            media_type=media_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения файла аватара {filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.delete(
    "/{user_id}",
    response_model=SuccessResponse,
    summary="Удаление аватара",
    description="Удаление аватара пользователя"
)
async def delete_avatar(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: CurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Удаление аватара пользователя"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = extract_role_name(current_user.get("role"))
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own avatar"
            )
        
        # Получаем профиль для получения имени файла аватара
        profile = await profile_service.get_profile_by_user_id(user_id)
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        avatar_filename = profile.get("avatar_filename")
        if not avatar_filename:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User has no avatar to delete"
            )
        
        # Удаляем файл аватара
        deleted = await avatar_service.delete_avatar(user_id, avatar_filename)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete avatar file"
            )
        
        # Обновляем профиль (убираем ссылку на аватар)
        await profile_service.update_profile(user_id, avatar_filename=None)
        
        logger.info(f"Удален аватар пользователя {user_id}")
        
        return SuccessResponse(
            message="Avatar deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления аватара пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{user_id}/variants",
    response_model=SuccessResponse,
    summary="Генерация вариантов аватара",
    description="Генерация различных размеров аватара пользователя"
)
async def generate_avatar_variants(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: CurrentUser = ...,
    profile_service: ProfileServiceDep = ...
):
    """Генерация различных размеров аватара"""
    try:
        # Проверяем права доступа
        current_user_id = current_user["id"]
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_id != user_id and current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only generate variants for your own avatar"
            )
        
        # Получаем профиль для получения имени файла аватара
        profile = await profile_service.get_profile_by_user_id(user_id)
        if not profile or profile.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        avatar_filename = profile.get("avatar_filename")
        if not avatar_filename:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User has no avatar"
            )
        
        # Генерируем варианты
        variants = await avatar_service.generate_avatar_variants(user_id, avatar_filename)
        
        if not variants:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate avatar variants"
            )
        
        logger.info(f"Сгенерированы варианты аватара для пользователя {user_id}: {len(variants)} файлов")
        
        return SuccessResponse(
            message=f"Generated {len(variants)} avatar variants",
            data={"variants": variants}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка генерации вариантов аватара для пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/{user_id}/cleanup",
    response_model=SuccessResponse,
    summary="Очистка аватаров",
    description="Очистка всех аватаров пользователя (только для администраторов)"
)
async def cleanup_user_avatars(
    user_id: int = Path(..., description="ID пользователя"),
    current_user: CurrentUser = ...
):
    """Очистка всех аватаров пользователя (только администраторы)"""
    try:
        # Проверяем права администратора
        current_user_role = current_user.get("role", {}).get("name", "")
        
        if current_user_role not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required"
            )
        
        # Очищаем аватары
        deleted_count = await avatar_service.cleanup_user_avatars(user_id)
        
        logger.info(f"Очищены аватары пользователя {user_id}: удалено {deleted_count} файлов")
        
        return SuccessResponse(
            message=f"Cleaned up {deleted_count} avatar files",
            data={"deleted_files": deleted_count}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка очистки аватаров пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )