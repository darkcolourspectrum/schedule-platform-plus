"""Studio Repository"""
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.studio import Studio

class StudioRepository(BaseRepository[Studio]):
    def __init__(self, db: AsyncSession):
        super().__init__(Studio, db)
    
    async def get_active_studios(self) -> List[Studio]:
        result = await self.db.execute(
            select(Studio).where(Studio.is_active == True)
        )
        return list(result.scalars().all())
    
    async def get_by_name(self, name: str) -> Optional[Studio]:
        result = await self.db.execute(
            select(Studio).where(Studio.name == name)
        )
        return result.scalar_one_or_none()
