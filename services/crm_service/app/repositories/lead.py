"""
Репозиторий для работы с лидами и их журналом активностей.

LeadActivity не имеет собственного репозитория: записи журнала всегда
создаются в контексте конкретного лида, отдельный CRUD для них не нужен.
Поэтому методы добавления активности живут здесь же.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.lead import Lead
from app.models.lead_activity import LeadActivity
from app.repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    """Доступ к данным лидов."""

    def __init__(self, db: AsyncSession):
        super().__init__(Lead, db)

    async def get_by_id_with_activities(self, lead_id: int) -> Optional[Lead]:
        """
        Получить лид вместе с загруженным журналом активностей.

        selectinload подгружает связанные LeadActivity одним отдельным
        запросом - без него обращение к lead.activities в async-контексте
        упало бы (ленивая загрузка в async SQLAlchemy запрещена).
        """
        result = await self.db.execute(
            select(Lead)
            .options(selectinload(Lead.activities))
            .where(Lead.id == lead_id)
        )
        return result.scalar_one_or_none()

    async def add_activity(self, activity: LeadActivity) -> LeadActivity:
        """
        Добавить запись в журнал активностей.

        Как и BaseRepository.add - делает flush, но не commit.
        Фиксацию делает сервисный слой в общей транзакции с лидом.
        """
        self.db.add(activity)
        await self.db.flush()
        await self.db.refresh(activity)
        return activity

    async def list_filtered(
        self,
        *,
        status: Optional[str] = None,
        assigned_to: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Lead], int]:
        """
        Получить страницу лидов с фильтрами.

        Фильтры (status, assigned_to) опциональны: None означает "не
        фильтровать по этому полю". Используются канбаном - выбрать лиды
        одной колонки воронки или лиды конкретного админа.

        Возвращает кортеж (лиды страницы, общее количество под фильтры).
        total считается отдельным запросом по тем же условиям, но без
        limit/offset - он нужен фронту для постраничной навигации.

        Сортировка - по убыванию created_at: свежие заявки сверху.
        """
        conditions = []
        if status is not None:
            conditions.append(Lead.status == status)
        if assigned_to is not None:
            conditions.append(Lead.assigned_to == assigned_to)

        # Запрос данных страницы.
        items_query = select(Lead)
        if conditions:
            items_query = items_query.where(*conditions)
        items_query = (
            items_query.order_by(Lead.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items_result = await self.db.execute(items_query)
        items = list(items_result.scalars().all())

        # Запрос общего количества под те же фильтры.
        count_query = select(func.count()).select_from(Lead)
        if conditions:
            count_query = count_query.where(*conditions)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        return items, total