from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.repositories.base import BaseRepository
from app.models.studio import Studio


class StudioRepository(BaseRepository[Studio]):
    """Репозиторий для работы со студиями"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Studio, db)
    
    async def get_by_auth_service_id(self, auth_service_studio_id: int) -> Optional[Studio]:
        """Получение студии по ID из Auth Service"""
        
        return await self.get_by_field(
            "auth_service_studio_id", 
            auth_service_studio_id,
            relationships=["rooms"]
        )
    
    async def get_active_studios(self) -> List[Studio]:
        """Получение всех активных студий"""
        
        query = select(Studio).options(
            selectinload(Studio.rooms)
        ).where(Studio.is_active == True).order_by(Studio.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def sync_from_auth_service(
        self,
        auth_service_studio_id: int,
        name: str,
        description: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        is_active: bool = True
    ) -> Studio:
        """
        Синхронизация данных студии с Auth Service
        Создает новую студию или обновляет существующую
        """
        
        existing_studio = await self.get_by_auth_service_id(auth_service_studio_id)
        
        studio_data = {
            "name": name,
            "description": description,
            "address": address,
            "phone": phone,
            "email": email,
            "is_active": is_active
        }
        
        if existing_studio:
            # Обновляем существующую студию
            updated_studio = await self.update(existing_studio.id, **studio_data)
            return updated_studio
        else:
            # Создаем новую студию
            studio_data["auth_service_studio_id"] = auth_service_studio_id
            return await self.create(**studio_data)
    
    async def get_studios_for_teacher(self, teacher_id: int) -> List[Studio]:
        """
        Получение студий, к которым имеет доступ преподаватель
        
        Note: Логика определения доступа должна быть реализована
        через интеграцию с Auth Service
        """
        # TODO: Интеграция с Auth Service для получения студий преподавателя
        # Пока возвращаем все активные студии
        return await self.get_active_studios()
    
    async def update_schedule_settings(
        self,
        studio_id: int,
        working_hours_start: Optional[str] = None,
        working_hours_end: Optional[str] = None,
        slot_duration_minutes: Optional[int] = None
    ) -> Optional[Studio]:
        """Обновление настроек расписания студии"""
        
        update_data = {}
        
        if working_hours_start:
            update_data["working_hours_start"] = working_hours_start
        
        if working_hours_end:
            update_data["working_hours_end"] = working_hours_end
        
        if slot_duration_minutes:
            update_data["slot_duration_minutes"] = slot_duration_minutes
        
        if update_data:
            return await self.update(studio_id, **update_data)
        
        return await self.get_by_id(studio_id)