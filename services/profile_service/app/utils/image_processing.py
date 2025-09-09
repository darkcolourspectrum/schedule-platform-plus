"""
Утилиты для обработки изображений
"""

import logging
from typing import Optional, Tuple, Union
from io import BytesIO
from PIL import Image, ImageOps
import asyncio

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Класс для обработки изображений"""
    
    def __init__(self):
        self.max_size = (1024, 1024)  # Максимальный размер по умолчанию
        self.quality = 85  # Качество JPEG по умолчанию
    
    async def process_avatar(
        self, 
        image_data: bytes, 
        max_size: Tuple[int, int] = (300, 300),
        quality: int = 85
    ) -> Optional[bytes]:
        """
        Обработка аватара пользователя
        
        Args:
            image_data: Байты изображения
            max_size: Максимальный размер (ширина, высота)
            quality: Качество JPEG (1-100)
            
        Returns:
            Обработанные байты изображения или None
        """
        try:
            # Выполняем обработку в отдельном потоке для больших изображений
            return await asyncio.get_event_loop().run_in_executor(
                None, 
                self._process_avatar_sync,
                image_data,
                max_size,
                quality
            )
        except Exception as e:
            logger.error(f"Ошибка асинхронной обработки аватара: {e}")
            return None
    
    def _process_avatar_sync(
        self, 
        image_data: bytes, 
        max_size: Tuple[int, int],
        quality: int
    ) -> Optional[bytes]:
        """Синхронная обработка аватара"""
        try:
            # Открываем изображение
            with Image.open(BytesIO(image_data)) as img:
                # Автоматически поворачиваем по EXIF
                img = ImageOps.exif_transpose(img)
                
                # Конвертируем в RGB если нужно
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Создаем белый фон для прозрачных изображений
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Делаем изображение квадратным (обрезаем по центру)
                img = self._make_square(img)
                
                # Изменяем размер
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Сохраняем в JPEG
                output = BytesIO()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                
                return output.getvalue()
                
        except Exception as e:
            logger.error(f"Ошибка обработки изображения: {e}")
            return None
    
    def _make_square(self, img: Image.Image) -> Image.Image:
        """Делает изображение квадратным, обрезая по центру"""
        try:
            width, height = img.size
            
            if width == height:
                return img
            
            # Определяем размер квадрата (меньшая сторона)
            size = min(width, height)
            
            # Вычисляем координаты для обрезки по центру
            left = (width - size) // 2
            top = (height - size) // 2
            right = left + size
            bottom = top + size
            
            # Обрезаем изображение
            return img.crop((left, top, right, bottom))
            
        except Exception as e:
            logger.error(f"Ошибка создания квадратного изображения: {e}")
            return img
    
    async def validate_image(self, image_data: bytes) -> dict:
        """
        Валидация изображения
        
        Args:
            image_data: Байты изображения
            
        Returns:
            Словарь с результатами валидации
        """
        try:
            with Image.open(BytesIO(image_data)) as img:
                width, height = img.size
                format_name = img.format
                mode = img.mode
                
                # Проверки
                checks = {
                    "is_valid": True,
                    "width": width,
                    "height": height,
                    "format": format_name,
                    "mode": mode,
                    "errors": []
                }
                
                # Проверяем минимальный размер
                if width < 32 or height < 32:
                    checks["errors"].append("Image too small (minimum 32x32)")
                    checks["is_valid"] = False
                
                # Проверяем максимальный размер
                if width > 4096 or height > 4096:
                    checks["errors"].append("Image too large (maximum 4096x4096)")
                    checks["is_valid"] = False
                
                # Проверяем формат
                if format_name not in ['JPEG', 'PNG', 'WEBP']:
                    checks["errors"].append(f"Unsupported format: {format_name}")
                    checks["is_valid"] = False
                
                return checks
                
        except Exception as e:
            logger.error(f"Ошибка валидации изображения: {e}")
            return {
                "is_valid": False,
                "errors": [f"Invalid image: {str(e)}"]
            }
    
    async def get_image_info(self, image_data: bytes) -> Optional[dict]:
        """
        Получение информации об изображении
        
        Args:
            image_data: Байты изображения
            
        Returns:
            Словарь с информацией об изображении
        """
        try:
            with Image.open(BytesIO(image_data)) as img:
                return {
                    "width": img.size[0],
                    "height": img.size[1],
                    "format": img.format,
                    "mode": img.mode,
                    "size_bytes": len(image_data),
                    "has_transparency": img.mode in ('RGBA', 'LA') or 'transparency' in img.info
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения информации об изображении: {e}")
            return None
    
    async def resize_image(
        self, 
        image_data: bytes,
        width: int,
        height: int,
        keep_aspect_ratio: bool = True,
        quality: int = 85
    ) -> Optional[bytes]:
        """
        Изменение размера изображения
        
        Args:
            image_data: Байты изображения
            width: Новая ширина
            height: Новая высота
            keep_aspect_ratio: Сохранять пропорции
            quality: Качество JPEG
            
        Returns:
            Измененное изображение в байтах
        """
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._resize_image_sync,
                image_data,
                width,
                height,
                keep_aspect_ratio,
                quality
            )
        except Exception as e:
            logger.error(f"Ошибка изменения размера изображения: {e}")
            return None
    
    def _resize_image_sync(
        self,
        image_data: bytes,
        width: int,
        height: int,
        keep_aspect_ratio: bool,
        quality: int
    ) -> Optional[bytes]:
        """Синхронное изменение размера изображения"""
        try:
            with Image.open(BytesIO(image_data)) as img:
                # Автоматически поворачиваем по EXIF
                img = ImageOps.exif_transpose(img)
                
                if keep_aspect_ratio:
                    # Используем thumbnail для сохранения пропорций
                    img.thumbnail((width, height), Image.Resampling.LANCZOS)
                else:
                    # Принудительно изменяем размер
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        if img.mode in ('RGBA', 'LA'):
                            background.paste(img, mask=img.split()[-1])
                        else:
                            background.paste(img)
                        img = background
                    else:
                        img = img.convert('RGB')
                
                # Сохраняем
                output = BytesIO()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                
                return output.getvalue()
                
        except Exception as e:
            logger.error(f"Ошибка синхронного изменения размера: {e}")
            return None
    
    async def create_thumbnail(
        self, 
        image_data: bytes,
        size: int = 64,
        quality: int = 85
    ) -> Optional[bytes]:
        """
        Создание миниатюры изображения
        
        Args:
            image_data: Байты изображения
            size: Размер миниатюры (квадрат)
            quality: Качество JPEG
            
        Returns:
            Миниатюра в байтах
        """
        return await self.resize_image(
            image_data=image_data,
            width=size,
            height=size,
            keep_aspect_ratio=False,  # Для миниатюр делаем точный размер
            quality=quality
        )