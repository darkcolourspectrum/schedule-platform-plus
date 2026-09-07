"""
Сервис для работы с расписанием (просмотр и фильтрация)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import date

from app.models.lesson import Lesson
from app.repositories.lesson_repository import LessonRepository
from app.repositories.user_repository import UserRepository
from app.schemas.schedule import ScheduleLessonItem
from app.repositories.classroom_cache_repository import ClassroomCacheRepository
from app.repositories.studio_cache_repository import StudioCacheRepository
from app.domain.recurrence import lesson_has_ended

logger = logging.getLogger(__name__)


class ScheduleService:
    """Сервис для работы с расписанием"""
    
    def __init__(
        self,
        lesson_repo: LessonRepository,
        user_repo: UserRepository,
        classroom_repo: ClassroomCacheRepository,
        studio_repo: StudioCacheRepository,
    ):
        self.lesson_repo = lesson_repo
        self.user_repo = user_repo
        self.classroom_repo = classroom_repo
        self.studio_repo = studio_repo

        # Памятки на время одного запроса. Сервис создаётся заново на
        # каждый HTTP-запрос, поэтому кеш не может протухнуть. В неделе
        # расписания одни и те же преподаватели и кабинеты повторяются
        # десятки раз - без памятки это десятки одинаковых SELECT.
        self._teacher_names: Dict[int, str] = {}
        self._classroom_names: Dict[int, str] = {}
    
    async def get_studio_schedule(
        self,
        studio_id: int,
        from_date: date,
        to_date: date
    ) -> List[ScheduleLessonItem]:
        """
        Получить расписание студии за период
        
        Автоматически догенерирует занятия если нужно
        """
        
        # Получаем занятия
        lessons = await self.lesson_repo.get_by_studio(studio_id, from_date, to_date)
        
        # Преобразуем в ScheduleLessonItem
        schedule_items = []
        for lesson in lessons:
            item = await self._lesson_to_schedule_item(lesson)
            schedule_items.append(item)
        
        return schedule_items
    
    async def get_teacher_schedule(
        self,
        teacher_id: int,
        from_date: date,
        to_date: date
    ) -> List[ScheduleLessonItem]:
        """Получить расписание преподавателя за период"""
        lessons = await self.lesson_repo.get_by_teacher(teacher_id, from_date, to_date)
        
        schedule_items = []
        for lesson in lessons:
            item = await self._lesson_to_schedule_item(lesson)
            schedule_items.append(item)
        
        return schedule_items
    
    async def get_student_schedule(
        self,
        student_id: int,
        from_date: date,
        to_date: date
    ) -> List[ScheduleLessonItem]:
        """Получить занятия ученика за период"""
        lessons = await self.lesson_repo.get_by_student(student_id, from_date, to_date)
        
        schedule_items = []
        for lesson in lessons:
            item = await self._lesson_to_schedule_item(lesson)
            schedule_items.append(item)
        
        return schedule_items

    async def _teacher_name(self, teacher_id: int) -> str:
        if teacher_id not in self._teacher_names:
            teacher = await self.user_repo.get_by_id(teacher_id)
            self._teacher_names[teacher_id] = (
                self.user_repo.get_full_name(teacher) if teacher else "Unknown"
            )
        return self._teacher_names[teacher_id]

    async def _classroom_name(self, classroom_id: Optional[int]) -> Optional[str]:
        """
        Настоящее название кабинета из локального кеша.

        Раньше здесь стояла заглушка f"Кабинет {id}", и пользователь
        видел номер вместо "Малый зал", хотя кеш кабинетов в сервисе
        уже был и использовался в других местах.
        """
        if classroom_id is None:
            return None
        if classroom_id not in self._classroom_names:
            classroom = await self.classroom_repo.get_by_id(classroom_id)
            self._classroom_names[classroom_id] = (
                classroom.name if classroom else f"Кабинет {classroom_id}"
            )
        return self._classroom_names[classroom_id]
    
    async def _lesson_to_schedule_item(self, lesson: Lesson) -> ScheduleLessonItem:
        """
        Преобразовать Lesson в ScheduleLessonItem с дополнительной информацией
        """
        # Получаем информацию о преподавателе
        teacher = await self.user_repo.get_by_id(lesson.teacher_id)
        teacher_name = await self._teacher_name(lesson.teacher_id)
        
        # Получаем учеников
        student_ids = await self.lesson_repo.get_student_ids(lesson.id)
        students = await self.user_repo.get_by_ids(student_ids) if student_ids else []
        student_names = [self.user_repo.get_full_name(s) for s in students]
        
        classroom_name = await self._classroom_name(lesson.classroom_id)
        
        return ScheduleLessonItem(
            lesson_id=lesson.id,
            lesson_date=lesson.lesson_date,
            start_time=lesson.start_time,
            end_time=lesson.end_time,
            status=lesson.status,
            teacher_id=lesson.teacher_id,
            teacher_name=teacher_name,
            classroom_id=lesson.classroom_id,
            classroom_name=classroom_name,
            student_ids=student_ids,
            student_names=student_names,
            is_recurring=lesson.recurring_pattern_id is not None,
            has_ended=lesson_has_ended(lesson.lesson_date, lesson.end_time),
            notes=lesson.notes
        )
    
    async def get_schedule_with_enrichment(
        self,
        lessons: List[Lesson],
        include_teacher_info: bool = True,
        include_student_info: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Получить расписание с обогащенной информацией
        (имена пользователей, кабинеты и т.д.)
        """
        enriched_lessons = []
        
        # Собираем все ID пользователей
        all_user_ids = set()
        if include_teacher_info:
            all_user_ids.update([lesson.teacher_id for lesson in lessons])
        
        if include_student_info:
            for lesson in lessons:
                student_ids = await self.lesson_repo.get_student_ids(lesson.id)
                all_user_ids.update(student_ids)
        
        # Загружаем всех пользователей одним запросом
        users = await self.user_repo.get_by_ids(list(all_user_ids)) if all_user_ids else []
        users_dict = {user.id: user for user in users}
        
        # Обогащаем данные
        for lesson in lessons:
            lesson_data = {
                "id": lesson.id,
                "lesson_date": lesson.lesson_date,
                "start_time": lesson.start_time,
                "end_time": lesson.end_time,
                "status": lesson.status,
                "classroom_id": lesson.classroom_id,
                "notes": lesson.notes,
                "is_recurring": lesson.recurring_pattern_id is not None
            }
            
            # Добавляем информацию о преподавателе
            if include_teacher_info and lesson.teacher_id in users_dict:
                teacher = users_dict[lesson.teacher_id]
                lesson_data["teacher"] = {
                    "id": teacher.id,
                    "name": self.user_repo.get_full_name(teacher),
                    "email": teacher.email
                }
            
            # Добавляем информацию об учениках
            if include_student_info:
                student_ids = await self.lesson_repo.get_student_ids(lesson.id)
                students_info = []
                for sid in student_ids:
                    if sid in users_dict:
                        student = users_dict[sid]
                        students_info.append({
                            "id": student.id,
                            "name": self.user_repo.get_full_name(student),
                            "email": student.email
                        })
                lesson_data["students"] = students_info
            
            enriched_lessons.append(lesson_data)
        
        return enriched_lessons

    async def get_lesson_names(self, lesson: Lesson) -> Dict[str, Any]:
        """
        Имена для карточки одного занятия.

        Живёт здесь, а не в LessonService: обогащение именами из локальных
        кешей - забота сервиса расписания, LessonService про кеши
        пользователей и кабинетов не знает и знать не должен.
        """
        student_ids = await self.lesson_repo.get_student_ids(lesson.id)
        students = await self.user_repo.get_by_ids(student_ids) if student_ids else []
        studio = await self.studio_repo.get_by_id(lesson.studio_id)

        return {
            "teacher_name": await self._teacher_name(lesson.teacher_id),
            "classroom_name": await self._classroom_name(lesson.classroom_id),
            "studio_name": studio.name if studio else None,
            "student_names": {
                student.id: self.user_repo.get_full_name(student)
                for student in students
            },
        }
