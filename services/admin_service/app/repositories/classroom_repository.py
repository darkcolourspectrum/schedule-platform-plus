"""Classroom Repository"""
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.repositories.base import BaseRepository
from app.models.classroom import Classroom

class ClassroomRepository(BaseRepository[Classroom]):
    def __init__(self, db: AsyncSession):
        super().__init__(Classroom, db)
    
    async def get_by_studio(self, studio_id: int) -> List[Classroom]:
        result = await self.db.execute(
            select(Classroom)
            .where(Classroom.studio_id == studio_id)
            .options(selectinload(Classroom.studio))
        )
        return list(result.scalars().all())
    
    async def get_active_by_studio(self, studio_id: int) -> List[Classroom]:
        result = await self.db.execute(
            select(Classroom)
            .where(Classroom.studio_id == studio_id, Classroom.is_active == True)
            .options(selectinload(Classroom.studio))
        )
        return list(result.scalars().all())
