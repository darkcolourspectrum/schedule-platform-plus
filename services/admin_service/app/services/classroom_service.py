"""Classroom Service"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.classroom_repository import ClassroomRepository
from app.models.classroom import Classroom

class ClassroomService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ClassroomRepository(db)
    
    async def get_studio_classrooms(self, studio_id: int) -> List[Classroom]:
        return await self.repo.get_by_studio(studio_id)
    
    async def get_classroom(self, classroom_id: int) -> Optional[Classroom]:
        return await self.repo.get_by_id(classroom_id)
    
    async def create_classroom(self, studio_id: int, **data) -> Classroom:
        return await self.repo.create(studio_id=studio_id, **data)
    
    async def update_classroom(self, classroom_id: int, **data) -> Optional[Classroom]:
        return await self.repo.update(classroom_id, **data)
    
    async def delete_classroom(self, classroom_id: int) -> bool:
        return await self.repo.delete(classroom_id)
