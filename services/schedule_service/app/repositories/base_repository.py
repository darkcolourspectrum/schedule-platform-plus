"""
Base repository с общими методами
"""

from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий с CRUD операциями"""
    
    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db
    
    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """Получить объект по ID"""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self, 
        limit: int = 100, 
        offset: int = 0,
        **filters
    ) -> List[ModelType]:
        """Получить все объекты с фильтрами"""
        query = select(self.model)
        
        # Применяем фильтры
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create(self, obj: ModelType) -> ModelType:
        """Создать объект"""
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    async def update_obj(self, obj: ModelType) -> ModelType:
        """Обновить объект"""
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    async def delete_by_id(self, id: int) -> bool:
        """Удалить объект по ID"""
        result = await self.db.execute(
            delete(self.model).where(self.model.id == id)
        )
        return result.rowcount > 0
    
    async def count(self, **filters) -> int:
        """Подсчитать количество объектов"""
        from sqlalchemy import func
        
        query = select(func.count(self.model.id))
        
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        
        result = await self.db.execute(query)
        return result.scalar_one()
    
    async def exists(self, **filters) -> bool:
        """Проверить существование объекта"""
        from sqlalchemy import exists as sql_exists
        
        query = select(sql_exists().where(self.model.id.isnot(None)))
        
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        
        result = await self.db.execute(query)
        return result.scalar()
