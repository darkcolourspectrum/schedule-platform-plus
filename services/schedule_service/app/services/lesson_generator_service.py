"""
Генерация занятий из шаблонов.

Файл переписан целиком. От прежней версии не осталось ничего, кроме
имени класса, потому что менялся сам принцип работы.

Было: курсор. Генератор находил последнее занятие шаблона и прибавлял
к его дате неделю. Из этого следовало всё сразу - дубли при разрыве
истории, игнорирование смены дня недели, безвозвратная потеря даты при
конфликте, зависимость результата от порядка вызовов.

Стало: сверка множеств. Генератор считает полное множество дат, на
которые должен попасть слот, вычитает уже существующие и создаёт разницу.
Результат зависит только от состояния данных, а не от истории вызовов.
Повторный запуск ничего не меняет.

Три операции:
    preview_pattern    посчитать, что получится, ничего не записывая
    generate_pattern   создать недостающее
    rollback_batch     отменить один прогон

Предпросмотр и генерация строят план одним и тем же кодом, поэтому
показанное пользователю число совпадает с тем, что будет создано.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, time
from typing import Dict, List, Optional, Sequence, Set, Tuple, Iterable
from uuid import UUID, uuid4

from app.domain.conflicts import (
    Conflict,
    ConflictReport,
    LessonCandidate,
)
from app.domain.recurrence import (
    calculate_end_time,
    generation_horizon_end,
    slot_occurrence_dates,
    today_in_studio_tz,
)

from app.messaging import (
    GeneratedLessonItem,
    record_generation_lessons_created,
    record_generation_lessons_deleted,
    DELETION_REASON_BATCH_ROLLED_BACK,
)

from app.models.recurring_pattern import RecurringPattern
from app.models.recurring_pattern_slot import RecurringPatternSlot
from app.repositories.lesson_generation_repository import (
    LessonGenerationRepository,
)
from app.services.conflict_service import ConflictService

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedLesson:
    """Занятие, которое генератор собирается создать."""

    slot_id: Optional[int]
    lesson_date: date
    start_time: time
    end_time: time
    teacher_id: int
    studio_id: int
    classroom_id: Optional[int]


@dataclass(frozen=True)
class BlockedLesson:
    """Занятие, которое создать нельзя, и причина."""

    slot_id: int
    lesson_date: date
    start_time: time
    end_time: time
    classroom_id: Optional[int]
    conflicts: Tuple[Conflict, ...]


@dataclass
class GenerationPlan:
    """
    Что произойдёт при генерации. Ничего не записано.

    Отдаётся предпросмотру как есть и используется генератором как
    инструкция. Одна структура на два сценария - гарантия того, что
    показанное число совпадёт с созданным.
    """

    to_create: List[PlannedLesson] = field(default_factory=list)
    blocked: List[BlockedLesson] = field(default_factory=list)
    already_exists_count: int = 0
    horizon_end: Optional[date] = None
    student_ids: Tuple[int, ...] = ()

    @property
    def will_create_count(self) -> int:
        return len(self.to_create)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked)

@dataclass(frozen=True)
class CreatedLesson:
    """
    Занятие, которое генератор действительно создал.

    От PlannedLesson отличается двумя вещами: у него есть id, выданный
    базой, и оно существует. План расходится с фактом, когда строку
    отбивает уникальный ключ или EXCLUDE-констрейнт, поэтому список
    собирается из ответа вставки, а не из плана.
    """

    lesson_id: int
    slot_id: Optional[int]
    lesson_date: date
    start_time: time
    end_time: time
    classroom_id: Optional[int]


@dataclass
class GenerationResult:
    """Итог фактической генерации."""

    batch_id: Optional[UUID]
    created_count: int
    blocked_count: int
    already_existed_count: int
    blocked: List[BlockedLesson] = field(default_factory=list)
    horizon_end: Optional[date] = None
    created: List[CreatedLesson] = field(default_factory=list)


class LessonGeneratorService:
    """Создание занятий из шаблонов повторения."""

    def __init__(
        self,
        generation_repo: LessonGenerationRepository,
        conflict_service: ConflictService,
        db: AsyncSession,
    ):
        """
        Args:
            db: та же сессия, на которой построен generation_repo.
                Нужна, чтобы записывать события в outbox той же
                транзакцией, что и сами занятия. Разные сессии здесь
                означали бы разные транзакции, а значит возможность
                опубликовать событие о занятиях, которых нет.
        """
        self.generation_repo = generation_repo
        self.conflict_service = conflict_service
        self.db = db

    # ==================== ПЛАНИРОВАНИЕ ====================

    async def build_plan(
        self,
        pattern: RecurringPattern,
        slots: Sequence[RecurringPatternSlot],
        student_ids: Sequence[int],
        until_date: Optional[date] = None,
        exclude_lesson_ids: Optional[Iterable[int]] = None,
    ) -> GenerationPlan:
        """
        Посчитать, какие занятия нужно создать. В БД ничего не пишется.

        Шаги:
            1. Для каждого слота посчитать целевые даты в горизонте.
            2. Вычесть даты, на которых занятие уже есть.
            3. Проверить остаток на конфликты по трём ресурсам.
            4. Разделить на "создаём" и "заблокировано".

        Args:
            pattern: шаблон с заполненными valid_from / valid_until /
                anchor_date / week_interval.
            slots: слоты шаблона. Для предпросмотра ещё не сохранённого
                шаблона сюда передаются несохранённые объекты с id=None.
            student_ids: ученики шаблона.
            until_date: до какой даты считать. По умолчанию - горизонт
                из настроек.
        """
        horizon_end = until_date or generation_horizon_end()

        if not pattern.is_active:
            logger.info(
                "Pattern %s is inactive, nothing to generate", pattern.id
            )
            return GenerationPlan(
                horizon_end=horizon_end,
                student_ids=tuple(student_ids),
            )

        # Шаг 1: целевые даты по каждому слоту.
        # Ключуем список парами, а не словарём по slot.id: при предпросмотре
        # несохранённого шаблона id у всех слотов None, и словарь схлопнул бы
        # их в одну запись.
        
        dates_per_slot: List[Tuple[RecurringPatternSlot, List[date]]] = []

        # Занятия не создаются задним числом. valid_from у давнего шаблона
        # может лежать в прошлом, и без этой границы генератор попытался бы
        # заполнить всю историю от даты начала действия.
        effective_from = max(pattern.valid_from, today_in_studio_tz())
        for slot in slots:
            dates_per_slot.append(
                (
                    slot,
                    slot_occurrence_dates(
                        day_of_week=slot.day_of_week,
                        valid_from=effective_from,
                        valid_until=pattern.valid_until,
                        anchor_date=pattern.anchor_date,
                        week_interval=pattern.week_interval,
                        horizon_end=horizon_end,
                    ),
                )
            )

        all_dates = [d for _slot, dates in dates_per_slot for d in dates]

        if not all_dates:
            return GenerationPlan(
                horizon_end=horizon_end,
                student_ids=tuple(student_ids),
            )

        # Шаг 2: что уже есть в БД. Диапазон сужаем до реальных дат,
        # а не до valid_from - у давнего шаблона это тысячи лишних строк.
        existing_by_slot = await self._fetch_existing(
            [slot for slot, _dates in dates_per_slot],
            min(all_dates),
            max(all_dates),
        )

        # Шаг 3: кандидаты из разницы множеств.
        candidates: List[LessonCandidate] = []
        planned: List[PlannedLesson] = []
        already_exists = 0

        for slot, target_dates in dates_per_slot:
            occupied = (
                existing_by_slot.get(slot.id, set()) if slot.id is not None else set()
            )
            end_time = calculate_end_time(slot.start_time, slot.duration_minutes)

            for lesson_date in target_dates:
                if lesson_date in occupied:
                    already_exists += 1
                    continue

                planned.append(
                    PlannedLesson(
                        slot_id=slot.id,
                        lesson_date=lesson_date,
                        start_time=slot.start_time,
                        end_time=end_time,
                        teacher_id=pattern.teacher_id,
                        studio_id=pattern.studio_id,
                        classroom_id=slot.classroom_id,
                    )
                )
                candidates.append(
                    LessonCandidate(
                        lesson_date=lesson_date,
                        start_time=slot.start_time,
                        end_time=end_time,
                        teacher_id=pattern.teacher_id,
                        classroom_id=slot.classroom_id,
                        student_ids=tuple(student_ids),
                        ref=str(slot.id),
                    )
                )

        if not candidates:
            return GenerationPlan(
                already_exists_count=already_exists,
                horizon_end=horizon_end,
                student_ids=tuple(student_ids),
            )

        # Шаг 4: конфликты.
        report = await self.conflict_service.check_candidates(
            candidates, exclude_lesson_ids=exclude_lesson_ids
        )

        return self._split_by_conflicts(
            planned=planned,
            report=report,
            already_exists=already_exists,
            horizon_end=horizon_end,
            student_ids=tuple(student_ids),
        )

    def _split_by_conflicts(
        self,
        *,
        planned: List[PlannedLesson],
        report: ConflictReport,
        already_exists: int,
        horizon_end: date,
        student_ids: Tuple[int, ...],
    ) -> GenerationPlan:
        """Разложить запланированное на создаваемое и заблокированное."""
        conflicts_by_index = report.by_candidate()
        blocked_indices = report.conflicting_indices

        to_create = [
            planned[i] for i in range(len(planned)) if i not in blocked_indices
        ]

        blocked = [
            BlockedLesson(
                slot_id=planned[i].slot_id,
                lesson_date=planned[i].lesson_date,
                start_time=planned[i].start_time,
                end_time=planned[i].end_time,
                classroom_id=planned[i].classroom_id,
                conflicts=tuple(conflicts_by_index.get(i, [])),
            )
            for i in sorted(blocked_indices)
        ]

        return GenerationPlan(
            to_create=to_create,
            blocked=blocked,
            already_exists_count=already_exists,
            horizon_end=horizon_end,
            student_ids=student_ids,
        )

    async def _fetch_existing(
        self,
        slots: Sequence[RecurringPatternSlot],
        from_date: date,
        to_date: date,
    ) -> Dict[int, Set[date]]:
        """
        Занятые даты по слотам.

        Слоты без id (предпросмотр несохранённого шаблона) пропускаются:
        занятий у них быть не может по определению.
        """
        saved_slot_ids = [slot.id for slot in slots if slot.id is not None]

        if not saved_slot_ids:
            return {}

        return await self.generation_repo.get_existing_dates_for_slots(
            saved_slot_ids, from_date, to_date
        )

    # ==================== ГЕНЕРАЦИЯ ====================

    async def generate_pattern(
        self,
        pattern: RecurringPattern,
        slots: Sequence[RecurringPatternSlot],
        student_ids: Sequence[int],
        until_date: Optional[date] = None,
    ) -> GenerationResult:
        """
        Создать недостающие занятия шаблона.

        Идемпотентна: повторный вызов на тех же данных создаст ноль
        занятий, потому что все целевые даты уже будут заняты.

        Не коммитит. Транзакцией управляет вызывающий слой -
        сервис или зависимость FastAPI, в соответствии с Unit of Work.
        """
        plan = await self.build_plan(pattern, slots, student_ids, until_date)

        if not plan.to_create:
            logger.info(
                "Pattern %s: nothing to generate (exists=%s, blocked=%s)",
                pattern.id,
                plan.already_exists_count,
                plan.blocked_count,
            )
            return GenerationResult(
                batch_id=None,
                created_count=0,
                blocked_count=plan.blocked_count,
                already_existed_count=plan.already_exists_count,
                blocked=plan.blocked,
                horizon_end=plan.horizon_end,
            )

        batch_id = uuid4()

        rows = [
            {
                "studio_id": item.studio_id,
                "teacher_id": item.teacher_id,
                "classroom_id": item.classroom_id,
                "recurring_pattern_id": pattern.id,
                "recurring_pattern_slot_id": item.slot_id,
                "lesson_date": item.lesson_date,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "status": "scheduled",
                "is_manually_modified": False,
                "generation_batch_id": batch_id,
            }
            for item in plan.to_create
        ]

        inserted = await self.generation_repo.insert_lessons(rows)

        if student_ids and inserted:
            pairs = [
                (lesson_id, student_id)
                for lesson_id, _slot_id, _lesson_date in inserted
                for student_id in student_ids
            ]
            await self.generation_repo.insert_lesson_students(pairs)

        # Сшиваем факт с планом. insert_lessons возвращает только
        # (id, slot_id, дата) - времени и кабинета там нет, а они нужны
        # и событию, и предстоящим напоминаниям. Ключ "слот + дата"
        # уникален по констрейнту uq_lesson_slot_date, поэтому
        # совпадение однозначно.
        planned_by_key = {
            (item.slot_id, item.lesson_date): item for item in plan.to_create
        }

        created: List[CreatedLesson] = []
        for lesson_id, slot_id, lesson_date in inserted:
            source = planned_by_key.get((slot_id, lesson_date))
            if source is None:
                # База вернула строку, которой нет в плане. Такого быть
                # не должно. Пропускаем молча в данных, но громко в логах:
                # выдумывать время и кабинет нельзя.
                logger.warning(
                    "Inserted lesson %s (slot %s, %s) is missing from plan",
                    lesson_id,
                    slot_id,
                    lesson_date,
                )
                continue

            created.append(
                CreatedLesson(
                    lesson_id=lesson_id,
                    slot_id=slot_id,
                    lesson_date=lesson_date,
                    start_time=source.start_time,
                    end_time=source.end_time,
                    classroom_id=source.classroom_id,
                )
            )
        
        # Расхождение между планом и фактом означает гонку: кто-то занял
        # слот между проверкой конфликтов и вставкой. База это отбила,
        # данные целы, но факт стоит зафиксировать в логах.
        if len(inserted) != len(rows):
            logger.warning(
                "Pattern %s: planned %s lessons, inserted %s. "
                "Разницу отбила база (параллельная запись)",
                pattern.id,
                len(rows),
                len(inserted),
            )

        logger.info(
            "Pattern %s: generated %s lessons, batch %s "
            "(existed=%s, blocked=%s, horizon=%s)",
            pattern.id,
            len(inserted),
            batch_id,
            plan.already_exists_count,
            plan.blocked_count,
            plan.horizon_end,
        )

        # Технический факт "в расписании появились строки". Пишется в ту
        # же транзакцию, что и сами занятия: событие о занятиях, которых
        # нет, невозможно в принципе - либо коммитится и то и другое,
        # либо ничего.
        #
        # Запись стоит здесь, а не у вызывающих, намеренно. generate_pattern
        # зовут из четырёх мест: создание шаблона, правка шаблона, ручной
        # эндпоинт генерации и ежечасное продление горизонта фоновым
        # воркером. Забыть публикацию в одном из них - вопрос времени,
        # и проявилось бы это тихо: занятия есть, аналитика их не видит.
        #
        # Рассыльщикам это событие не достанется: очереди notification
        # и vk_bot привязаны к ключу 'lesson.*', а здесь 'generation.*'.
        
        await record_generation_lessons_created(
            self.db,
            pattern_id=pattern.id,
            batch_id=batch_id,
            studio_id=pattern.studio_id,
            teacher_id=pattern.teacher_id,
            student_ids=list(student_ids),
            lessons=[
                GeneratedLessonItem(
                    lesson_id=item.lesson_id,
                    slot_id=item.slot_id,
                    lesson_date=item.lesson_date.isoformat(),
                    start_time=item.start_time.isoformat(),
                    end_time=item.end_time.isoformat(),
                    classroom_id=item.classroom_id,
                )
                for item in created
            ],
        )

        return GenerationResult(
            batch_id=batch_id,
            created_count=len(inserted),
            blocked_count=plan.blocked_count,
            already_existed_count=plan.already_exists_count,
            blocked=plan.blocked,
            horizon_end=plan.horizon_end,
            created=created,
        )

    async def remove_future_lessons_for_slots(
        self,
        *,
        slot_ids: Sequence[int],
        pattern_id: int,
        reason: str,
    ) -> List[int]:
        """
        Удалить будущие несостоявшиеся занятия слотов и записать событие.

        Обёртка над репозиторием, добавляющая к удалению его публичную
        половину. Живёт здесь, а не в RecurringPatternService, по той же
        причине, по которой здесь же стоит публикация о создании: все
        события потока generation.* собраны в одном месте, и добавление
        нового пути удаления не может тихо остаться без события.

        Условия удаления задаёт репозиторий: только будущее, только
        статус scheduled, только занятия без ручных правок.

        Args:
            reason: одна из DELETION_REASON_* из app.messaging. Уходит
                в payload и нужна при разборе расхождений в аналитике.

        Returns:
            ID удалённых занятий.

        Не коммитит.
        """
        deleted_ids = await self.generation_repo.delete_future_lessons_for_slots(
            slot_ids=slot_ids,
            not_before=today_in_studio_tz(),
        )

        await record_generation_lessons_deleted(
            self.db,
            lesson_ids=deleted_ids,
            reason=reason,
            pattern_id=pattern_id,
        )

        return deleted_ids

    # ==================== ОТКАТ ====================

    async def rollback_batch(self, batch_id: UUID) -> int:
        """
        Отменить прогон генерации.

        Удаляет только будущие занятия этого прогона, не тронутые вручную
        и не проведённые. Ошибка в настройке шаблона перестаёт быть
        необратимой: одно действие возвращает расписание к прежнему виду.

        Returns:
        Количество удалённых занятий.
        """
        deleted_lesson_ids = await self.generation_repo.delete_generation_batch(
            batch_id=batch_id,
            not_before=today_in_studio_tz(),
        )

        await record_generation_lessons_deleted(
            self.db,
            lesson_ids=deleted_lesson_ids,
            reason=DELETION_REASON_BATCH_ROLLED_BACK,
            batch_id=batch_id,
        )

        return len(deleted_lesson_ids)