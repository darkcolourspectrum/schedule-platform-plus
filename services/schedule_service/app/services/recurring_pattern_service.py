"""
Сервис шаблонов повторяющихся занятий.

Файл переписан под модель со слотами.

Главное отличие от прежней версии - обновление шаблона больше не является
операцией "поменяли поля и забыли". Раньше правка шаблона вообще никак не
отражалась на уже созданных занятиях: комментарий в старом эндпоинте так
и говорил, "уже созданные занятия не изменяются". Практически это значило,
что перенос занятия с вторника на четверг приходилось делать вручную по
всему расписанию.

Теперь при изменении расписания шаблона будущие занятия пересобираются,
а прошлое и ручные правки остаются нетронутыми.

Три правила, которые делают это безопасным:

    1. Граница "сегодня". Всё, что раньше сегодняшней даты в часовом поясе
       студии, не трогается никогда. История посещений неприкосновенна.

    2. Флаг is_manually_modified. Занятие, которое админ перенёс или
       изменил руками, перегенерация обходит стороной. Без этого правка
       шаблона стирала бы все ручные исключения - классическая причина,
       по которой расписание проще развернуть заново, чем чинить.

    3. Только статус scheduled. Проведённое, отменённое или пропущенное
       занятие - это факт, а не план. Пересборка их не касается.
"""

import logging
from datetime import date
from typing import List, Optional, Sequence, Tuple

from app.core.exceptions import RecurringPatternNotFoundException
from app.domain.conflicts import Conflict, ConflictKind
from app.domain.recurrence import (
    DAY_NAMES,
    calculate_end_time,
    today_in_studio_tz,
)
from app.models.recurring_pattern import RecurringPattern
from app.models.recurring_pattern_slot import RecurringPatternSlot
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.lesson_generation_repository import (
    LessonGenerationRepository,
)
from app.repositories.recurring_pattern_repository import (
    RecurringPatternRepository,
)
from app.schemas.recurring_pattern import (
    PreviewConflictItem,
    RecurringPatternCreate,
    RecurringPatternPreviewRequest,
    RecurringPatternUpdate,
)
from app.services.lesson_generator_service import (
    BlockedLesson,
    GenerationPlan,
    GenerationResult,
    LessonGeneratorService,
)

from app.messaging import (
    DELETION_REASON_PATTERN_DELETED,
    DELETION_REASON_PATTERN_UPDATED,
    PatternSlotItem,
    record_pattern_assigned,
    record_pattern_changed,
    record_pattern_unassigned,
)

logger = logging.getLogger(__name__)


CONFLICT_MESSAGES = {
    ConflictKind.CLASSROOM: "Кабинет занят другим занятием",
    ConflictKind.TEACHER: "У преподавателя другое занятие в это время",
    ConflictKind.STUDENT: "Ученик занят на другом занятии",
}


class RecurringPatternService:
    """Создание, изменение и удаление шаблонов вместе с их занятиями."""

    def __init__(
        self,
        pattern_repo: RecurringPatternRepository,
        generation_repo: LessonGenerationRepository,
        generator_service: LessonGeneratorService,
        db: AsyncSession,
    ):
        """
        Args:
            db: та же сессия, что у репозиториев. Нужна для записи
                событий в outbox одной транзакцией с изменением шаблона.
        """
        self.pattern_repo = pattern_repo
        self.generation_repo = generation_repo
        self.generator_service = generator_service
        self.db = db

    # ==================== СЛУЖЕБНОЕ ====================

    @staticmethod
    def _slot_items(slots: Sequence[RecurringPatternSlot]) -> List[PatternSlotItem]:
        """
        Слоты шаблона в форме, пригодной для события.

        end_time в слотах не хранится - в БД лежит длительность.
        Считается тем же calculate_end_time, что и при создании занятий:
        в сообщении ученику должно стоять ровно то время, которое стоит
        в расписании, а не пересчитанное вторым способом.
        """
        return [
            PatternSlotItem(
                day_of_week=slot.day_of_week,
                day_name=DAY_NAMES[slot.day_of_week],
                start_time=slot.start_time.isoformat(),
                end_time=calculate_end_time(
                    slot.start_time, slot.duration_minutes
                ).isoformat(),
                classroom_id=slot.classroom_id,
            )
            for slot in slots
        ]

    @staticmethod
    def _slots_differ(
        before: Sequence[PatternSlotItem],
        after: Sequence[PatternSlotItem],
    ) -> bool:
        """
        Изменился ли набор слотов по существу.

        Порядок слотов в форме значения не имеет, поэтому сравниваются
        отсортированные наборы. Нужно, чтобы не писать ученику "было
        вторник 18:00, стало вторник 18:00", когда сохранили форму,
        ничего в ней не тронув, - фронт присылает слоты при каждом
        сохранении, даже если правили только заметку.
        """
        def signature(items: Sequence[PatternSlotItem]):
            return sorted(
                (item.day_of_week, item.start_time, item.end_time, item.classroom_id)
                for item in items
            )

        return signature(before) != signature(after)

    # ==================== ЧТЕНИЕ ====================

    async def get_pattern(self, pattern_id: int) -> RecurringPattern:
        """Шаблон со слотами и учениками."""
        pattern = await self.pattern_repo.get_by_id_full(pattern_id)
        if not pattern:
            raise RecurringPatternNotFoundException(pattern_id)
        return pattern

    async def get_patterns_by_studio(
        self, studio_id: int, active_only: bool = True
    ) -> List[RecurringPattern]:
        return await self.pattern_repo.get_by_studio(studio_id, active_only)

    async def get_patterns_by_teacher(
        self, teacher_id: int, active_only: bool = True
    ) -> List[RecurringPattern]:
        return await self.pattern_repo.get_by_teacher(teacher_id, active_only)

    async def get_pattern_student_ids(self, pattern_id: int) -> List[int]:
        return await self.pattern_repo.get_student_ids(pattern_id)

    async def count_generated_lessons(self, pattern_id: int) -> int:
        return await self.generation_repo.count_lessons_for_pattern(pattern_id)

    # ==================== ПРЕДПРОСМОТР ====================

    async def preview(
        self, data: RecurringPatternPreviewRequest
    ) -> GenerationPlan:
        """
        Посчитать результат, ничего не записывая.

        Собирает временные объекты RecurringPattern и слотов, не добавляя
        их в сессию, и прогоняет через тот же build_plan, что и настоящая
        генерация. Одинаковый код - гарантия, что показанное число совпадёт
        с созданным.

        Объекты создаются, но не попадают в session.add, поэтому в БД
        ничего не уходит даже при последующем коммите.
        """
        pattern = RecurringPattern(
            studio_id=data.studio_id,
            teacher_id=data.teacher_id,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            week_interval=data.week_interval,
            anchor_date=data.valid_from,
            is_active=True,
            notes=data.notes,
        )
        pattern.id = data.pattern_id

        slots = [
            RecurringPatternSlot(
                day_of_week=item.day_of_week,
                start_time=item.start_time,
                duration_minutes=item.duration_minutes,
                classroom_id=item.classroom_id,
            )
            for item in data.slots
        ]

        # Занятия редактируемого шаблона исключаем из проверки: при
        # сохранении update_pattern сначала удалит будущие занятия старых
        # слотов и только потом сгенерирует новые. Без исключения
        # предпросмотр показывал бы конфликт шаблона с самим собой.
        exclude_lesson_ids: List[int] = []
        if data.pattern_id:
            exclude_lesson_ids = await self.generation_repo.get_lesson_ids_for_pattern(
                data.pattern_id,
                not_before=today_in_studio_tz(),
            )

        return await self.generator_service.build_plan(
            pattern=pattern,
            slots=slots,
            student_ids=data.student_ids,
            exclude_lesson_ids=exclude_lesson_ids,
        )

    # ==================== СОЗДАНИЕ ====================

    async def create_pattern(
        self, data: RecurringPatternCreate
    ) -> Tuple[RecurringPattern, GenerationResult]:
        """
        Создать шаблон и сгенерировать занятия на горизонт.

        Не коммитит: шаблон, слоты, ученики и занятия сохраняются одной
        транзакцией на уровне зависимости FastAPI. Если генерация упадёт,
        шаблон тоже не сохранится - половинчатого состояния не будет.
        """
        pattern = RecurringPattern(
            studio_id=data.studio_id,
            teacher_id=data.teacher_id,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            week_interval=data.week_interval,
            # Опорная дата фиксируется один раз и дальше не меняется:
            # иначе правка valid_from переворачивала бы чётность недель
            # и вся сетка занятий уезжала бы на неделю.
            anchor_date=data.valid_from,
            is_active=True,
            notes=data.notes,
        )

        pattern = await self.pattern_repo.create(pattern)

        slots = await self.pattern_repo.replace_slots(
            pattern.id,
            [item.model_dump() for item in data.slots],
        )

        for student_id in data.student_ids:
            await self.pattern_repo.add_student(pattern.id, student_id)

        result = await self.generator_service.generate_pattern(
            pattern=pattern,
            slots=slots,
            student_ids=data.student_ids,
        )

        # Факт "ученику назначили регулярные занятия".
        # Уходит рассыльщикам той же транзакцией, что и сам шаблон.
        #
        # Даты берём из БД, а не из result: занятия только что созданы
        # в этой же транзакции и видны текущей сессии, а логика "какие
        # даты назвать ученику" оказывается одна на создание и на правку.
        if data.student_ids:
            upcoming_dates = await self.generation_repo.get_future_scheduled_lesson_dates(
                pattern_id=pattern.id,
                not_before=today_in_studio_tz(),
            )
            await record_pattern_assigned(
                self.db,
                pattern_id=pattern.id,
                studio_id=pattern.studio_id,
                teacher_id=pattern.teacher_id,
                student_ids=list(data.student_ids),
                slots=self._slot_items(slots),
                upcoming_dates=upcoming_dates,
                valid_until=pattern.valid_until,
            )

        logger.info(
            "Created pattern %s with %s slots, generated %s lessons",
            pattern.id,
            len(slots),
            result.created_count,
        )

        return pattern, result

    # ==================== ОБНОВЛЕНИЕ ====================

    async def update_pattern(
        self, pattern_id: int, data: RecurringPatternUpdate
    ) -> Tuple[RecurringPattern, GenerationResult]:
        """
        Обновить шаблон и пересобрать будущие занятия.

        Порядок операций важен и не может быть другим:

            1. Удалить будущие занятия старых слотов. Именно СЕЙЧАС, пока
               связь recurring_pattern_slot_id ещё цела. После замены слотов
               найти эти занятия будет нельзя: FK стоит на ondelete=SET NULL,
               и они превратятся в неотличимые от разовых.

            2. Заменить слоты.

            3. Сгенерировать заново на горизонт.

        Расписание пересобирается только если менялось что-то, влияющее на
        даты: слоты, период действия, периодичность. Правка заметок даты
        занятий не трогает.

        Состав учеников - отдельная история. Он не влияет на даты, поэтому
        пересборку не запускает, но должен доехать до уже созданных будущих
        занятий: добавленного ученика надо в них вписать, убранного -
        вычеркнуть. Без этого шаблон и занятия расходятся, и расписание
        ученика показывает не то, что записано в шаблоне.
        """
        pattern = await self.get_pattern(pattern_id)
        today = today_in_studio_tz()

        schedule_changed = (
            data.slots is not None
            or data.valid_from is not None
            or data.valid_until is not None
            or data.week_interval is not None
        )

        if schedule_changed:
            old_slot_ids = [slot.id for slot in pattern.slots]
            deleted_lesson_ids = await self.generator_service.remove_future_lessons_for_slots(
                slot_ids=old_slot_ids,
                pattern_id=pattern_id,
                reason=DELETION_REASON_PATTERN_UPDATED,
            )
            logger.info(
                "Pattern %s update: removed %s future lessons before rebuild",
                pattern_id,
                len(deleted_lesson_ids),
            )

        if data.valid_from is not None:
            pattern.valid_from = data.valid_from
        if data.valid_until is not None:
            pattern.valid_until = data.valid_until
        if data.week_interval is not None:
            pattern.week_interval = data.week_interval
        if data.is_active is not None:
            pattern.is_active = data.is_active
        if data.notes is not None:
            pattern.notes = data.notes

        # Снимок прежнего расписания. Именно снимок значений, а не список
        # ORM-объектов: replace_slots ниже удалит эти строки, SQLAlchemy
        # пометит объекты удалёнными и обесценит их атрибуты, и любое
        # последующее обращение к slot.day_of_week попытается сходить
        # за обновлением в БД - синхронно, из async-кода. Это и есть
        # MissingGreenlet. PatternSlotItem - обычные значения, они
        # переживают что угодно.
        previous_slot_items = self._slot_items(pattern.slots)

        if data.slots is not None:
            slots = await self.pattern_repo.replace_slots(
                pattern_id,
                [item.model_dump() for item in data.slots],
            )
        else:
            slots = list(pattern.slots)

        # Прежний состав фиксируем ДО обновления связей: после
        # update_students узнать его будет уже негде.
        previous_student_ids = [item.student_id for item in pattern.students]

        if data.student_ids is not None:
            await self.pattern_repo.update_students(pattern_id, data.student_ids)
            student_ids = list(data.student_ids)

            added_student_ids = [
                item for item in student_ids if item not in previous_student_ids
            ]
            removed_student_ids = [
                item for item in previous_student_ids if item not in student_ids
            ]

            if added_student_ids or removed_student_ids:
                # Занятия, которые переживут эту правку. Если расписание
                # менялось, обычные будущие занятия уже удалены выше и
                # здесь останутся только правленные вручную - им состав
                # тоже надо поправить, иначе снятый ученик так и будет
                # числиться на перенесённом занятии.
                lesson_ids = await self.generation_repo.get_future_scheduled_lesson_ids(
                    pattern_id=pattern_id,
                    not_before=today,
                )

                if lesson_ids:
                    if added_student_ids:
                        await self.generation_repo.insert_lesson_students(
                            [
                                (lesson_id, student_id)
                                for lesson_id in lesson_ids
                                for student_id in added_student_ids
                            ]
                        )
                    if removed_student_ids:
                        await self.generation_repo.delete_lesson_students(
                            lesson_ids=lesson_ids,
                            student_ids=removed_student_ids,
                        )

                logger.info(
                    "Pattern %s: student roster changed, +%s -%s on %s lessons",
                    pattern_id,
                    len(added_student_ids),
                    len(removed_student_ids),
                    len(lesson_ids),
                )
        else:
            student_ids = await self.pattern_repo.get_student_ids(pattern_id)
            added_student_ids = []
            removed_student_ids = []

        pattern = await self.pattern_repo.update_obj(pattern)

        # Пересборка занятий. Делается до событий: сообщение ученику
        # должно называть даты, которые уже существуют.
        if schedule_changed:
            result = await self.generator_service.generate_pattern(
                pattern=pattern,
                slots=slots,
                student_ids=student_ids,
            )
            logger.info(
                "Updated pattern %s, regenerated %s lessons",
                pattern_id,
                result.created_count,
            )
        else:
            result = GenerationResult(
                batch_id=None,
                created_count=0,
                blocked_count=0,
                already_existed_count=0,
            )

        # ---- события для рассыльщиков ----
        #
        # Три разных факта и три разных адресата. В одном сохранении
        # формы могут случиться все три сразу: расписание сдвинули,
        # кого-то добавили, кого-то сняли.
        #
        #   добавленным   "вам назначены занятия"   - они не знают,
        #                 каким расписание было раньше, и рассказывать
        #                 им про изменение бессмысленно;
        #   оставшимся    "расписание изменилось"   - только если оно
        #                 действительно изменилось;
        #   снятым        "занятия отменены"        - их занятия уже
        #                 удалены, узнать об этом больше неоткуда.
        #
        # Правка одних лишь заметок не порождает ничего: слоты приходят
        # с каждым сохранением формы, поэтому смотрим на их содержимое,
        # а не на факт присутствия в запросе.
        slot_items = self._slot_items(slots)
        schedule_really_changed = self._slots_differ(previous_slot_items, slot_items)

        remaining_student_ids = [
            item for item in student_ids if item not in added_student_ids
        ]

        upcoming_dates: List[date] = []
        if added_student_ids or (schedule_really_changed and remaining_student_ids):
            upcoming_dates = await self.generation_repo.get_future_scheduled_lesson_dates(
                pattern_id=pattern_id,
                not_before=today,
            )

        if added_student_ids:
            await record_pattern_assigned(
                self.db,
                pattern_id=pattern_id,
                studio_id=pattern.studio_id,
                teacher_id=pattern.teacher_id,
                student_ids=added_student_ids,
                slots=slot_items,
                upcoming_dates=upcoming_dates,
                valid_until=pattern.valid_until,
            )

        if schedule_really_changed and remaining_student_ids:
            await record_pattern_changed(
                self.db,
                pattern_id=pattern_id,
                studio_id=pattern.studio_id,
                teacher_id=pattern.teacher_id,
                student_ids=remaining_student_ids,
                slots=slot_items,
                previous_slots=previous_slot_items,
                upcoming_dates=upcoming_dates,
                valid_until=pattern.valid_until,
            )

        if removed_student_ids:
            await record_pattern_unassigned(
                self.db,
                pattern_id=pattern_id,
                studio_id=pattern.studio_id,
                teacher_id=pattern.teacher_id,
                student_ids=removed_student_ids,
                previous_slots=previous_slot_items,
            )

        return pattern, result

    # ==================== УДАЛЕНИЕ И ДЕАКТИВАЦИЯ ====================

    async def deactivate_pattern(self, pattern_id: int) -> RecurringPattern:
        """
        Выключить шаблон.

        Новые занятия перестают генерироваться, уже созданные остаются.
        Это штатный способ прекратить регулярные занятия: расписание
        доживает до конца горизонта и дальше не продлевается.
        """
        pattern = await self.get_pattern(pattern_id)
        pattern.is_active = False
        pattern = await self.pattern_repo.update_obj(pattern)
        logger.info("Deactivated pattern %s", pattern_id)
        return pattern

    async def delete_pattern(
        self, pattern_id: int, delete_future_lessons: bool = False
    ) -> int:
        """
        Удалить шаблон.

        Args:
            delete_future_lessons: удалить ли будущие занятия. По умолчанию
                нет - занятия остаются в расписании, просто теряют связь
                с шаблоном (FK на ondelete=SET NULL).

        Прошлые занятия не удаляются никогда, независимо от флага.
        Удаление шаблона не должно стирать историю посещений: раньше
        это происходило само собой из-за cascade="all, delete-orphan"
        на связи, и было исправлено в блоке 1.

        Returns:
            Количество удалённых будущих занятий.
        """
        pattern = await self.get_pattern(pattern_id)
        deleted_lesson_ids: List[int] = []

        if delete_future_lessons:
            deleted_lesson_ids = await self.generator_service.remove_future_lessons_for_slots(
                slot_ids=[slot.id for slot in pattern.slots],
                pattern_id=pattern_id,
                reason=DELETION_REASON_PATTERN_DELETED,
            )

        await self.pattern_repo.delete_by_id(pattern_id)
        logger.info(
            "Deleted pattern %s, removed %s future lessons",
            pattern_id,
            len(deleted_lesson_ids),
        )
        return len(deleted_lesson_ids)

    # ==================== ПРЕОБРАЗОВАНИЕ ДЛЯ ОТВЕТА ====================

    @staticmethod
    def conflicts_to_items(
        blocked: Sequence[BlockedLesson],
    ) -> List[PreviewConflictItem]:
        """
        Развернуть заблокированные занятия в плоский список для API.

        Имена кабинетов, преподавателей и учеников не подставляются:
        у фронта уже есть справочники, а тянуть их здесь означало бы
        лишние запросы к трём кешам ради текста подсказки.
        """
        items: List[PreviewConflictItem] = []

        for entry in blocked:
            for conflict in entry.conflicts:
                items.append(
                    PreviewConflictItem(
                        lesson_date=entry.lesson_date,
                        start_time=entry.start_time,
                        end_time=entry.end_time,
                        kind=conflict.kind.value,
                        subject_id=conflict.subject_id,
                        classroom_id=entry.classroom_id,
                        message=CONFLICT_MESSAGES.get(
                            conflict.kind, "Время занято"
                        ),
                    )
                )

        return items