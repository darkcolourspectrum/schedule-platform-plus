from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.repositories.base import BaseRepository
from app.models.room import Room, RoomType


class RoomRepository(BaseRepository[Room]):
    """Репозиторий для работы с кабинетами"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Room, db)
    
    async def get_studio_rooms(self, studio_id: int, active_only: bool = True) -> List[Room]:
        """Получение всех кабинетов студии"""
        
        query = select(Room).where(Room.studio_id == studio_id)
        
        if active_only:
            query = query.where(Room.is_active == True)
        
        query = query.order_by(Room.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_rooms_by_type(self, studio_id: int, room_type: RoomType) -> List[Room]:
        """Получение кабинетов определенного типа"""
        
        query = select(Room).where(
            and_(
                Room.studio_id == studio_id,
                Room.room_type == room_type,
                Room.is_active == True
            )
        ).order_by(Room.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_suitable_rooms(
        self,
        studio_id: int,
        min_capacity: int = 1,
        needs_piano: bool = False,
        needs_microphone: bool = False,
        needs_recording: bool = False
    ) -> List[Room]:
        """Получение подходящих кабинетов по требованиям"""
        
        filters = [
            Room.studio_id == studio_id,
            Room.is_active == True,
            Room.max_capacity >= min_capacity
        ]
        
        if needs_piano:
            filters.append(Room.has_piano == True)
        
        if needs_microphone:
            filters.append(Room.has_microphone == True)
        
        if needs_recording:
            filters.append(Room.has_recording_equipment == True)
        
        query = select(Room).where(and_(*filters)).order_by(Room.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create_room(
        self,
        studio_id: int,
        name: str,
        room_type: RoomType = RoomType.VOCAL_SMALL,
        description: Optional[str] = None,
        max_capacity: int = 2,
        **equipment_options
    ) -> Room:
        """Создание нового кабинета с указанным оборудованием"""
        
        room_data = {
            "studio_id": studio_id,
            "name": name,
            "room_type": room_type,
            "description": description,
            "max_capacity": max_capacity,
            # Значения по умолчанию для вокальной студии
            "has_piano": equipment_options.get("has_piano", True),
            "has_microphone": equipment_options.get("has_microphone", True),
            "has_mirror": equipment_options.get("has_mirror", True),
            "has_sound_system": equipment_options.get("has_sound_system", True),
            "has_recording_equipment": equipment_options.get("has_recording_equipment", False),
            "area_sqm": equipment_options.get("area_sqm"),
            "floor_number": equipment_options.get("floor_number", 1)
        }
        
        return await self.create(**room_data)