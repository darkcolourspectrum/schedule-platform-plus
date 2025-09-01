from typing import TypeVar, Generic, Type, Optional, List, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий для CRUD операций"""
    
    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db
    
    async def get_by_id(
        self, 
        id: Any,
        relationships: Optional[List[str]] = None
    ) -> Optional[ModelType]:
        """Получение записи по ID с возможностью загрузки связей"""
        query = select(self.model).where(self.model.id == id)
        
        if relationships:
            for rel in relationships:
                query = query.options(selectinload(getattr(self.model, rel)))
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_field(
        self, 
        field: str, 
        value: Any,
        relationships: Optional[List[str]] = None
    ) -> Optional[ModelType]:
        """Получение записи по полю"""
        query = select(self.model).where(getattr(self.model, field) == value)
        
        if relationships:
            for rel in relationships:
                query = query.options(selectinload(getattr(self.model, rel)))
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_all(
        self, 
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        relationships: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        **filters
    ) -> List[ModelType]:
        """Получение всех записей с фильтрами"""
        query = select(self.model)
        
        # Применяем фильтры
        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        
        if relationships:
            for rel in relationships:
                query = query.options(selectinload(getattr(self.model, rel)))
        
        # Сортировка
        if order_by and hasattr(self.model, order_by):
            query = query.order_by(getattr(self.model, order_by))
        
        if offset:
            query = query.offset(offset)
        
        if limit:
            query = query.limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create(self, **data) -> ModelType:
        """Создание новой записи"""
        instance = self.model(**data)
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)
        return instance
    
    async def update(
        self, 
        id: Any, 
        **data
    ) -> Optional[ModelType]:
        """Обновление записи по ID"""
        query = (
            update(self.model)
            .where(self.model.id == id)
            .values(**data)
            .returning(self.model)
        )
        
        result = await self.db.execute(query)
        await self.db.commit()
        return result.scalar_one_or_none()
    
    async def delete(self, id: Any) -> bool:
        """Удаление записи по ID"""
        query = delete(self.model).where(self.model.id == id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0
    
    async def exists(self, **filters) -> bool:
        """Проверка существования записи"""
        query = select(self.model)
        
        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        
        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none() is not None
    
    async def count(self, **filters) -> int:
        """Подсчет записей с фильтрами"""
        query = select(func.count(self.model.id))
        
        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        
        result = await self.db.execute(query)
        return result.scalar()