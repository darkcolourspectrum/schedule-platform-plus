"""Studio Service"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.studio_repository import StudioRepository
from app.models.studio import Studio

class StudioService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StudioRepository(db)
    
    async def get_all_studios(self, include_inactive: bool = False) -> List[Studio]:
        if include_inactive:
            return await self.repo.get_all()
        return await self.repo.get_active_studios()
    
    async def get_studio(self, studio_id: int) -> Optional[Studio]:
        return await self.repo.get_by_id(studio_id)
    
    async def create_studio(self, **data) -> Studio:
        return await self.repo.create(**data)
    
    async def update_studio(self, studio_id: int, **data) -> Optional[Studio]:
        return await self.repo.update(studio_id, **data)
    
    async def delete_studio(self, studio_id: int) -> bool:
        return await self.repo.delete(studio_id)
