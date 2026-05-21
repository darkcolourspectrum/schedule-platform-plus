"""
Базовый репозиторий для CRM Service.

Транзакционная политика (паттерн Unit of Work, как в auth/schedule):
    Репозиторий НЕ управляет транзакциями. Методы вызывают flush(),
    а не commit() - изменения становятся видны внутри текущей сессии,
    но фиксация откладывается до явного commit() в сервисном слое.

    Это значит: одна бизнес-операция = одна транзакция, в которую могут
    входить несколько вызовов репозитория (например, создать лид + дописать
    запись в журнал активностей + позже записать событие в outbox).

    Сервисный слой обязан вызвать commit() после успешного завершения
    операции. Rollback при ошибке делает FastAPI-зависимость get_db.
"""

from typing import Any, Generic, Optional, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий с типовыми CRUD-операциями."""

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """Получить объект по первичному ключу."""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def add(self, instance: ModelType) -> ModelType:
        """
        Добавить новый объект в сессию.

        Делает flush (объект получает id и становится виден внутри
        транзакции), но НЕ commit - фиксацию делает сервисный слой.
        """
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def count(self, **filters: Any) -> int:
        """Подсчитать количество объектов с равенством по фильтрам."""
        query = select(func.count()).select_from(self.model)
        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)
        result = await self.db.execute(query)
        return result.scalar_one()