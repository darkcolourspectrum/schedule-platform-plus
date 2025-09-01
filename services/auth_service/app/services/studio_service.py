from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.repositories.base import BaseRepository
from app.models.studio import Studio
from app.models.user import User
from app.core.exceptions import UserNotFoundException, ValidationException
from app.schemas.admin import StudioCreate, StudioUpdate, StudioInfo


class StudioRepository(BaseRepository[Studio]):
    """Репозиторий для работы со студиями"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Studio, db)
    
    async def get_studios_with_user_counts(self) -> List[dict]:
        """Получение студий с количеством пользователей"""
        
        # Подсчет преподавателей
        teachers_subquery = (
            select(
                User.studio_id,
                func.count(User.id).label('teachers_count')
            )
            .join(User.role)
            .where(User.role.has(name='teacher'))
            .group_by(User.studio_id)
            .subquery()
        )
        
        # Подсчет студентов (привязанных к студии)
        students_subquery = (
            select(
                User.studio_id,
                func.count(User.id).label('students_count')
            )
            .join(User.role)
            .where(User.role.has(name='student'))
            .where(User.studio_id.isnot(None))
            .group_by(User.studio_id)
            .subquery()
        )
        
        # Основной запрос
        query = (
            select(
                Studio,
                func.coalesce(teachers_subquery.c.teachers_count, 0).label('teachers_count'),
                func.coalesce(students_subquery.c.students_count, 0).label('students_count')
            )
            .outerjoin(teachers_subquery, Studio.id == teachers_subquery.c.studio_id)
            .outerjoin(students_subquery, Studio.id == students_subquery.c.studio_id)
        )
        
        result = await self.db.execute(query)
        return [
            {
                'studio': row.Studio,
                'teachers_count': row.teachers_count,
                'students_count': row.students_count
            }
            for row in result
        ]


class StudioService:
    """Сервис для работы со студиями"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.studio_repo = StudioRepository(db)
    
    async def get_all_studios_with_stats(self) -> List[StudioInfo]:
        """Получение всех студий с статистикой"""
        
        studios_data = await self.studio_repo.get_studios_with_user_counts()
        
        return [
            StudioInfo(
                id=data['studio'].id,
                name=data['studio'].name,
                description=data['studio'].description,
                address=data['studio'].address,
                phone=data['studio'].phone,
                email=data['studio'].email,
                is_active=data['studio'].is_active,
                teachers_count=data['teachers_count'],
                students_count=data['students_count'],
                created_at=data['studio'].created_at
            )
            for data in studios_data
        ]
    
    async def get_studio_with_stats(self, studio_id: int) -> Optional[StudioInfo]:
        """Получение студии с статистикой"""
        
        studios_data = await self.studio_repo.get_studios_with_user_counts()
        studio_data = next((data for data in studios_data if data['studio'].id == studio_id), None)
        
        if not studio_data:
            return None
        
        return StudioInfo(
            id=studio_data['studio'].id,
            name=studio_data['studio'].name,
            description=studio_data['studio'].description,
            address=studio_data['studio'].address,
            phone=studio_data['studio'].phone,
            email=studio_data['studio'].email,
            is_active=studio_data['studio'].is_active,
            teachers_count=studio_data['teachers_count'],
            students_count=studio_data['students_count'],
            created_at=studio_data['studio'].created_at
        )
    
    async def create_studio(self, studio_data: StudioCreate) -> StudioInfo:
        """Создание новой студии"""
        
        # Проверка уникальности названия
        existing = await self.studio_repo.get_by_field('name', studio_data.name)
        if existing:
            raise ValidationException("Studio with this name already exists")
        
        studio = await self.studio_repo.create(**studio_data.dict())
        
        return StudioInfo(
            id=studio.id,
            name=studio.name,
            description=studio.description,
            address=studio.address,
            phone=studio.phone,
            email=studio.email,
            is_active=studio.is_active,
            teachers_count=0,
            students_count=0,
            created_at=studio.created_at
        )
    
    async def update_studio(self, studio_id: int, update_data: StudioUpdate) -> StudioInfo:
        """Обновление студии"""
        
        # Получаем только не None значения
        update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
        
        if not update_dict:
            # Если нет данных для обновления, возвращаем существующую студию
            return await self.get_studio_with_stats(studio_id)
        
        updated_studio = await self.studio_repo.update(studio_id, **update_dict)
        
        if not updated_studio:
            raise UserNotFoundException()
        
        return await self.get_studio_with_stats(studio_id)
    
    async def deactivate_studio(self, studio_id: int) -> Studio:
        """Деактивация студии"""
        
        studio = await self.studio_repo.update(studio_id, is_active=False)
        if not studio:
            raise UserNotFoundException()
        
        return studio
    
    async def activate_studio(self, studio_id: int) -> Studio:
        """Активация студии"""
        
        studio = await self.studio_repo.update(studio_id, is_active=True)
        if not studio:
            raise UserNotFoundException()
        
        return studio
    
    async def get_studio_teachers(self, studio_id: int) -> List[dict]:
        """Получение преподавателей студии"""
        
        query = (
            select(User)
            .join(User.role)
            .where(User.studio_id == studio_id)
            .where(User.role.has(name='teacher'))
            .where(User.is_active == True)
        )
        
        result = await self.db.execute(query)
        teachers = result.scalars().all()
        
        return [
            {
                "id": teacher.id,
                "email": teacher.email,
                "full_name": teacher.full_name,
                "phone": teacher.phone,
                "last_login": teacher.last_login,
                "is_active": teacher.is_active
            }
            for teacher in teachers
        ]