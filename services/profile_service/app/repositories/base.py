"""
Базовый репозиторий для Profile Service
"""

from typing import TypeVar, Generic, Optional, List, Dict, Any, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func, and_, or_
from sqlalchemy.exc import SQLAlchemyError
import logging

from app.models.base import BaseModel

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий с CRUD операциями"""
    
    def __init__(self, model: type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db
    
    async def create(self, **kwargs) -> Optional[ModelType]:
        """
        Создание новой записи
        
        Args:
            **kwargs: Данные для создания
            
        Returns:
            Созданная запись или None при ошибке
        """
        try:
            instance = self.model(**kwargs)
            self.db.add(instance)
            await self.db.commit()
            await self.db.refresh(instance)
            
            logger.debug(f"Создана запись {self.model.__name__} с ID {instance.id}")
            return instance
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка создания {self.model.__name__}: {e}")
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[ModelType]:
        """
        Получение записи по ID
        
        Args:
            record_id: ID записи
            
        Returns:
            Найденная запись или None
        """
        try:
            result = await self.db.execute(
                select(self.model).where(self.model.id == record_id)
            )
            instance = result.scalar_one_or_none()
            
            if instance:
                logger.debug(f"Найдена запись {self.model.__name__} с ID {record_id}")
            else:
                logger.debug(f"Запись {self.model.__name__} с ID {record_id} не найдена")
            
            return instance
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения {self.model.__name__} по ID {record_id}: {e}")
            return None
    
    async def get_all(
        self, 
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> List[ModelType]:
        """
        Получение всех записей
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            order_by: Поле для сортировки
            
        Returns:
            Список записей
        """
        try:
            query = select(self.model)
            
            # Сортировка
            if order_by:
                if hasattr(self.model, order_by):
                    query = query.order_by(getattr(self.model, order_by))
                else:
                    query = query.order_by(self.model.id)
            else:
                query = query.order_by(self.model.id)
            
            # Пагинация
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            result = await self.db.execute(query)
            instances = result.scalars().all()
            
            logger.debug(f"Получено {len(instances)} записей {self.model.__name__}")
            return list(instances)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения всех {self.model.__name__}: {e}")
            return []
    
    async def update(
        self, 
        record_id: int, 
        **kwargs
    ) -> Optional[ModelType]:
        """
        Обновление записи
        
        Args:
            record_id: ID записи
            **kwargs: Данные для обновления
            
        Returns:
            Обновленная запись или None
        """
        try:
            # Получаем существующую запись
            instance = await self.get_by_id(record_id)
            if not instance:
                logger.warning(f"Запись {self.model.__name__} с ID {record_id} не найдена для обновления")
                return None
            
            # Обновляем поля
            for key, value in kwargs.items():
                if hasattr(instance, key) and key != 'id':
                    setattr(instance, key, value)
            
            await self.db.commit()
            await self.db.refresh(instance)
            
            logger.debug(f"Обновлена запись {self.model.__name__} с ID {record_id}")
            return instance
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления {self.model.__name__} с ID {record_id}: {e}")
            return None
    
    async def delete(self, record_id: int) -> bool:
        """
        Удаление записи
        
        Args:
            record_id: ID записи
            
        Returns:
            True если запись удалена, False иначе
        """
        try:
            result = await self.db.execute(
                delete(self.model).where(self.model.id == record_id)
            )
            await self.db.commit()
            
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.debug(f"Удалена запись {self.model.__name__} с ID {record_id}")
                return True
            else:
                logger.warning(f"Запись {self.model.__name__} с ID {record_id} не найдена для удаления")
                return False
                
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка удаления {self.model.__name__} с ID {record_id}: {e}")
            return False
    
    async def exists(self, record_id: int) -> bool:
        """
        Проверка существования записи
        
        Args:
            record_id: ID записи
            
        Returns:
            True если запись существует
        """
        try:
            result = await self.db.execute(
                select(func.count(self.model.id)).where(self.model.id == record_id)
            )
            count = result.scalar()
            return count > 0
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка проверки существования {self.model.__name__} с ID {record_id}: {e}")
            return False
    
    async def count(self, **filters) -> int:
        """
        Подсчет количества записей с фильтрами
        
        Args:
            **filters: Фильтры для подсчета
            
        Returns:
            Количество записей
        """
        try:
            query = select(func.count(self.model.id))
            
            # Применяем фильтры
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
            
            result = await self.db.execute(query)
            count = result.scalar()
            
            logger.debug(f"Подсчитано {count} записей {self.model.__name__} с фильтрами {filters}")
            return count or 0
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка подсчета {self.model.__name__}: {e}")
            return 0
    
    async def find_by(self, **filters) -> List[ModelType]:
        """
        Поиск записей по фильтрам
        
        Args:
            **filters: Фильтры для поиска
            
        Returns:
            Список найденных записей
        """
        try:
            query = select(self.model)
            
            # Применяем фильтры
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
            
            result = await self.db.execute(query)
            instances = result.scalars().all()
            
            logger.debug(f"Найдено {len(instances)} записей {self.model.__name__} с фильтрами {filters}")
            return list(instances)
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка поиска {self.model.__name__}: {e}")
            return []
    
    async def find_one_by(self, **filters) -> Optional[ModelType]:
        """
        Поиск одной записи по фильтрам
        
        Args:
            **filters: Фильтры для поиска
            
        Returns:
            Найденная запись или None
        """
        try:
            query = select(self.model)
            
            # Применяем фильтры
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
            
            result = await self.db.execute(query)
            instance = result.scalar_one_or_none()
            
            if instance:
                logger.debug(f"Найдена запись {self.model.__name__} с фильтрами {filters}")
            else:
                logger.debug(f"Запись {self.model.__name__} с фильтрами {filters} не найдена")
            
            return instance
            
        except SQLAlchemyError as e:
            logger.error(f"Ошибка поиска одной записи {self.model.__name__}: {e}")
            return None
    
    async def bulk_create(self, records_data: List[Dict[str, Any]]) -> List[ModelType]:
        """
        Массовое создание записей
        
        Args:
            records_data: Список данных для создания записей
            
        Returns:
            Список созданных записей
        """
        try:
            instances = []
            for data in records_data:
                instance = self.model(**data)
                instances.append(instance)
                self.db.add(instance)
            
            await self.db.commit()
            
            # Обновляем записи для получения ID
            for instance in instances:
                await self.db.refresh(instance)
            
            logger.debug(f"Массово создано {len(instances)} записей {self.model.__name__}")
            return instances
            
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Ошибка массового создания {self.model.__name__}: {e}")
            return []