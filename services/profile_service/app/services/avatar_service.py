"""
Сервис для работы с аватарами пользователей
"""

import logging
import os
import uuid
from typing import Optional, Dict, Any, Tuple
from PIL import Image
import aiofiles
from fastapi import UploadFile

from app.config import settings
from app.utils.image_processing import ImageProcessor

logger = logging.getLogger(__name__)


class AvatarService:
    """Сервис для работы с аватарами пользователей"""
    
    def __init__(self):
        self.upload_path = settings.avatar_upload_full_path
        self.max_size_bytes = settings.max_avatar_size_bytes
        self.allowed_types = settings.allowed_image_types
        self.image_processor = ImageProcessor()
    
    async def upload_avatar(
        self, 
        user_id: int, 
        file: UploadFile
    ) -> Dict[str, Any]:
        """
        Загрузка и обработка аватара пользователя
        
        Args:
            user_id: ID пользователя
            file: Загружаемый файл
            
        Returns:
            Словарь с результатом загрузки
        """
        try:
            # Валидация файла
            validation_result = await self._validate_upload_file(file)
            if not validation_result["valid"]:
                logger.warning(f"Невалидный файл аватара от пользователя {user_id}: {validation_result['error']}")
                return {
                    "success": False,
                    "error": validation_result["error"]
                }
            
            # Создаем уникальное имя файла
            file_extension = self._get_file_extension(file.filename)
            filename = f"user_{user_id}_{uuid.uuid4().hex}{file_extension}"
            filepath = os.path.join(self.upload_path, filename)
            
            # Читаем содержимое файла
            file_content = await file.read()
            
            # Обрабатываем изображение
            processed_image = await self.image_processor.process_avatar(
                image_data=file_content,
                max_size=(300, 300),  # Стандартный размер аватара
                quality=85
            )
            
            if not processed_image:
                logger.error(f"Не удалось обработать изображение для пользователя {user_id}")
                return {
                    "success": False,
                    "error": "Failed to process image"
                }
            
            # Сохраняем обработанное изображение
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(processed_image)
            
            # Удаляем старый аватар если есть
            await self._cleanup_old_avatars(user_id, filename)
            
            logger.info(f"Аватар пользователя {user_id} успешно загружен: {filename}")
            
            return {
                "success": True,
                "filename": filename,
                "url": f"/static/avatars/{filename}",
                "size": len(processed_image)
            }
            
        except Exception as e:
            logger.error(f"Ошибка загрузки аватара для пользователя {user_id}: {e}")
            return {
                "success": False,
                "error": "Upload failed"
            }
    
    async def delete_avatar(
        self, 
        user_id: int, 
        filename: str
    ) -> bool:
        """
        Удаление аватара пользователя
        
        Args:
            user_id: ID пользователя
            filename: Имя файла аватара
            
        Returns:
            True если аватар удален успешно
        """
        try:
            # Проверяем, что файл принадлежит пользователю
            if not filename.startswith(f"user_{user_id}_"):
                logger.warning(f"Попытка удалить чужой аватар: {filename} пользователем {user_id}")
                return False
            
            filepath = os.path.join(self.upload_path, filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Аватар пользователя {user_id} удален: {filename}")
                return True
            else:
                logger.warning(f"Файл аватара не найден: {filepath}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка удаления аватара {filename} пользователя {user_id}: {e}")
            return False
    
    async def get_avatar_info(
        self, 
        filename: str
    ) -> Optional[Dict[str, Any]]:
        """
        Получение информации об аватаре
        
        Args:
            filename: Имя файла аватара
            
        Returns:
            Словарь с информацией об аватаре или None
        """
        try:
            filepath = os.path.join(self.upload_path, filename)
            
            if not os.path.exists(filepath):
                return None
            
            # Получаем информацию о файле
            file_stats = os.stat(filepath)
            
            # Получаем размеры изображения
            try:
                with Image.open(filepath) as img:
                    width, height = img.size
                    format_name = img.format
            except Exception:
                width = height = 0
                format_name = "Unknown"
            
            return {
                "filename": filename,
                "url": f"/static/avatars/{filename}",
                "size_bytes": file_stats.st_size,
                "width": width,
                "height": height,
                "format": format_name,
                "created_at": file_stats.st_ctime,
                "modified_at": file_stats.st_mtime
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения информации об аватаре {filename}: {e}")
            return None
    
    async def generate_avatar_variants(
        self, 
        user_id: int, 
        original_filename: str
    ) -> Dict[str, str]:
        """
        Генерация различных размеров аватара
        
        Args:
            user_id: ID пользователя
            original_filename: Имя оригинального файла
            
        Returns:
            Словарь с именами файлов различных размеров
        """
        try:
            original_path = os.path.join(self.upload_path, original_filename)
            
            if not os.path.exists(original_path):
                logger.warning(f"Оригинальный файл аватара не найден: {original_path}")
                return {}
            
            # Размеры для генерации
            sizes = {
                "thumbnail": (64, 64),    # Миниатюра
                "small": (128, 128),      # Маленький
                "medium": (256, 256),     # Средний
                "large": (512, 512)       # Большой
            }
            
            variants = {}
            base_name = original_filename.rsplit('.', 1)[0]
            extension = self._get_file_extension(original_filename)
            
            # Читаем оригинальное изображение
            async with aiofiles.open(original_path, 'rb') as f:
                original_data = await f.read()
            
            # Генерируем варианты
            for size_name, (width, height) in sizes.items():
                variant_filename = f"{base_name}_{size_name}{extension}"
                variant_path = os.path.join(self.upload_path, variant_filename)
                
                # Обрабатываем изображение
                processed_image = await self.image_processor.process_avatar(
                    image_data=original_data,
                    max_size=(width, height),
                    quality=85
                )
                
                if processed_image:
                    # Сохраняем вариант
                    async with aiofiles.open(variant_path, 'wb') as f:
                        await f.write(processed_image)
                    
                    variants[size_name] = variant_filename
                    logger.debug(f"Создан вариант аватара {size_name}: {variant_filename}")
            
            logger.info(f"Созданы варианты аватара для пользователя {user_id}: {len(variants)} файлов")
            return variants
            
        except Exception as e:
            logger.error(f"Ошибка генерации вариантов аватара для пользователя {user_id}: {e}")
            return {}
    
    async def cleanup_user_avatars(self, user_id: int) -> int:
        """
        Очистка всех аватаров пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество удаленных файлов
        """
        try:
            deleted_count = 0
            prefix = f"user_{user_id}_"
            
            # Перебираем все файлы в папке аватаров
            for filename in os.listdir(self.upload_path):
                if filename.startswith(prefix):
                    filepath = os.path.join(self.upload_path, filename)
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.debug(f"Удален файл аватара: {filename}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления файла {filename}: {e}")
            
            logger.info(f"Очистка аватаров пользователя {user_id}: удалено {deleted_count} файлов")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Ошибка очистки аватаров пользователя {user_id}: {e}")
            return 0
    
    # Приватные методы
    
    async def _validate_upload_file(self, file: UploadFile) -> Dict[str, Any]:
        """Валидация загружаемого файла"""
        try:
            # Проверяем размер файла
            if hasattr(file, 'size') and file.size:
                if file.size > self.max_size_bytes:
                    return {
                        "valid": False,
                        "error": f"File too large. Max size: {settings.max_avatar_size_mb}MB"
                    }
            
            # Проверяем тип файла
            if file.content_type not in self.allowed_types:
                return {
                    "valid": False,
                    "error": f"Invalid file type. Allowed: {', '.join(self.allowed_types)}"
                }
            
            # Проверяем расширение файла
            if not file.filename:
                return {
                    "valid": False,
                    "error": "Filename is required"
                }
            
            extension = self._get_file_extension(file.filename).lower()
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']
            
            if extension not in allowed_extensions:
                return {
                    "valid": False,
                    "error": f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}"
                }
            
            return {"valid": True}
            
        except Exception as e:
            logger.error(f"Ошибка валидации файла: {e}")
            return {
                "valid": False,
                "error": "Validation failed"
            }
    
    def _get_file_extension(self, filename: str) -> str:
        """Получение расширения файла"""
        if not filename:
            return ".jpg"  # По умолчанию
        
        parts = filename.lower().split('.')
        if len(parts) > 1:
            extension = f".{parts[-1]}"
            # Нормализуем расширения
            if extension in ['.jpeg']:
                return '.jpg'
            return extension
        
        return ".jpg"  # По умолчанию
    
    async def _cleanup_old_avatars(self, user_id: int, new_filename: str):
        """Удаление старых аватаров пользователя (кроме нового)"""
        try:
            prefix = f"user_{user_id}_"
            deleted_count = 0
            
            for filename in os.listdir(self.upload_path):
                if filename.startswith(prefix) and filename != new_filename:
                    filepath = os.path.join(self.upload_path, filename)
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.debug(f"Удален старый аватар: {filename}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления старого аватара {filename}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Удалено {deleted_count} старых аватаров пользователя {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых аватаров пользователя {user_id}: {e}")


# Глобальный экземпляр сервиса аватаров
avatar_service = AvatarService()