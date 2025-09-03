from typing import List, Optional
from datetime import datetime, date, time, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.repositories.base import BaseRepository
from app.models.time_slot import TimeSlot, SlotStatus
from app.models.studio import Studio
from app.models.room import Room


class TimeSlotRepository(BaseRepository[TimeSlot]):
    """Репозиторий для работы с временными слотами"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(TimeSlot, db)
    
    async def get_available_slots(
        self,
        studio_id: int,
        start_date: date,
        end_date: date,
        room_id: Optional[int] = None
    ) -> List[TimeSlot]:
        """Получение доступных слотов для бронирования в заданном диапазоне"""
        
        query = select(TimeSlot).options(
            selectinload(TimeSlot.studio),
            selectinload(TimeSlot.room)
        ).where(
            and_(
                TimeSlot.studio_id == studio_id,
                TimeSlot.date >= start_date,
                TimeSlot.date <= end_date,
                TimeSlot.status == SlotStatus.AVAILABLE
            )
        )
        
        if room_id:
            query = query.where(TimeSlot.room_id == room_id)
        
        query = query.order_by(TimeSlot.date, TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_teacher_slots(
        self,
        teacher_id: int,
        start_date: date,
        end_date: date,
        include_completed: bool = False
    ) -> List[TimeSlot]:
        """Получение слотов конкретного преподавателя"""
        
        statuses = [SlotStatus.RESERVED, SlotStatus.BOOKED]
        if include_completed:
            statuses.append(SlotStatus.COMPLETED)
        
        query = select(TimeSlot).options(
            selectinload(TimeSlot.studio),
            selectinload(TimeSlot.room),
            selectinload(TimeSlot.lesson)
        ).where(
            and_(
                TimeSlot.reserved_by_teacher_id == teacher_id,
                TimeSlot.date >= start_date,
                TimeSlot.date <= end_date,
                TimeSlot.status.in_(statuses)
            )
        ).order_by(TimeSlot.date, TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_studio_schedule(
        self,
        studio_id: int,
        target_date: date,
        room_id: Optional[int] = None
    ) -> List[TimeSlot]:
        """Получение расписания студии на конкретный день"""
        
        query = select(TimeSlot).options(
            selectinload(TimeSlot.room),
            selectinload(TimeSlot.lesson)
        ).where(
            and_(
                TimeSlot.studio_id == studio_id,
                TimeSlot.date == target_date
            )
        )
        
        if room_id:
            query = query.where(TimeSlot.room_id == room_id)
        
        query = query.order_by(TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def check_slot_conflict(
        self,
        room_id: int,
        date: date,
        start_time: time,
        end_time: time,
        exclude_slot_id: Optional[int] = None
    ) -> bool:
        """Проверка конфликта временных слотов"""
        
        query = select(TimeSlot).where(
            and_(
                TimeSlot.room_id == room_id,
                TimeSlot.date == date,
                TimeSlot.status != SlotStatus.AVAILABLE,  # Любой занятый слот
                or_(
                    # Новый слот начинается во время существующего
                    and_(
                        TimeSlot.start_time <= start_time,
                        TimeSlot.end_time > start_time
                    ),
                    # Новый слот заканчивается во время существующего
                    and_(
                        TimeSlot.start_time < end_time,
                        TimeSlot.end_time >= end_time
                    ),
                    # Новый слот полностью охватывает существующий
                    and_(
                        TimeSlot.start_time >= start_time,
                        TimeSlot.end_time <= end_time
                    )
                )
            )
        )
        
        if exclude_slot_id:
            query = query.where(TimeSlot.id != exclude_slot_id)
        
        result = await self.db.execute(query)
        conflict_slot = result.scalar_one_or_none()
        
        return conflict_slot is not None
    
    async def create_slot(
        self,
        studio_id: int,
        room_id: int,
        date: date,
        start_time: time,
        duration_minutes: int
    ) -> Optional[TimeSlot]:
        """Создание нового временного слота с проверкой конфликтов"""
        
        # Вычисляем время окончания
        start_datetime = datetime.combine(date, start_time)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        end_time = end_datetime.time()
        
        # Проверяем конфликты
        has_conflict = await self.check_slot_conflict(
            room_id=room_id,
            date=date,
            start_time=start_time,
            end_time=end_time
        )
        
        if has_conflict:
            return None
        
        return await self.create(
            studio_id=studio_id,
            room_id=room_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            status=SlotStatus.AVAILABLE
        )
    
    async def generate_weekly_slots(
        self,
        studio_id: int,
        room_ids: List[int],
        start_date: date,
        working_hours_start: time,
        working_hours_end: time,
        slot_duration_minutes: int = 60
    ) -> List[TimeSlot]:
        """
        Генерация слотов на неделю для указанных кабинетов
        
        Returns:
            List[TimeSlot]: Список созданных слотов
        """
        
        created_slots = []
        
        # Генерируем слоты на 7 дней
        for day_offset in range(7):
            current_date = start_date + timedelta(days=day_offset)
            
            for room_id in room_ids:
                # Генерируем слоты с заданным интервалом
                current_time = working_hours_start
                
                while current_time < working_hours_end:
                    # Проверяем, что слот помещается в рабочие часы
                    end_datetime = datetime.combine(current_date, current_time) + timedelta(minutes=slot_duration_minutes)
                    
                    if end_datetime.time() <= working_hours_end:
                        slot = await self.create_slot(
                            studio_id=studio_id,
                            room_id=room_id,
                            date=current_date,
                            start_time=current_time,
                            duration_minutes=slot_duration_minutes
                        )
                        
                        if slot:
                            created_slots.append(slot)
                    
                    # Переходим к следующему слоту
                    next_datetime = datetime.combine(current_date, current_time) + timedelta(minutes=slot_duration_minutes)
                    current_time = next_datetime.time()
        
        return created_slots
    
    async def reserve_slot_for_teacher(
        self,
        slot_id: int,
        teacher_id: int,
        teacher_name: str,
        teacher_email: str
    ) -> bool:
        """Резервирование слота преподавателем"""
        
        slot = await self.get_by_id(slot_id)
        if not slot:
            return False
        
        success = slot.reserve_for_teacher(teacher_id, teacher_name, teacher_email)
        if success:
            await self.db.commit()
        
        return success
    
    async def release_teacher_reservation(
        self,
        slot_id: int,
        teacher_id: int
    ) -> bool:
        """Снятие резервирования слота преподавателем"""
        
        slot = await self.get_by_id(slot_id)
        if not slot:
            return False
        
        success = slot.release_reservation(teacher_id)
        if success:
            await self.db.commit()
        
        return success
    
    async def get_studio_schedule_range(
        self,
        studio_id: int,
        start_date: date,
        end_date: date
    ) -> List[TimeSlot]:
        """Получение всех слотов студии в диапазоне дат"""
        
        query = select(TimeSlot).options(
            selectinload(TimeSlot.room),
            selectinload(TimeSlot.lesson)
        ).where(
            and_(
                TimeSlot.studio_id == studio_id,
                TimeSlot.date >= start_date,
                TimeSlot.date <= end_date
            )
        ).order_by(TimeSlot.date, TimeSlot.start_time)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_upcoming_teacher_slots(
        self,
        teacher_id: int,
        days_ahead: int = 7
    ) -> List[TimeSlot]:
        """Получение предстоящих слотов преподавателя"""
        
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        return await self.get_teacher_slots(
            teacher_id=teacher_id,
            start_date=start_date,
            end_date=end_date,
            include_completed=False
        )