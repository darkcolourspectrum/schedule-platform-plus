"""
Массовые операции над занятиями при генерации из шаблонов.

Вынесено из LessonRepository отдельно: там штучные операции над одним
занятием, здесь пакетные над десятками. У них разные требования -
пакетным нужны ON CONFLICT, savepoint'ы и работа множествами.

Ключевая идея: вставка идемпотентна. Повторный прогон генерации на тех
же данных не создаёт дублей, потому что конфликт по уникальному ключу
(recurring_pattern_slot_id, lesson_date) молча пропускается. Это делает
безопасным и повторный вызов, и параллельный запуск двух генераций.
"""

import logging
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson import Lesson
from app.models.lesson_student import LessonStudent

logger = logging.getLogger(__name__)


# Кортеж (id занятия, id слота, дата) - результат вставки.
InsertedRow = Tuple[int, Optional[int], date]


class LessonGenerationRepository:
    """Пакетные вставки и удаления занятий."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_existing_dates_for_slots(
        self,
        slot_ids: Sequence[int],
        from_date: date,
        to_date: date,
    ) -> Dict[int, Set[date]]:
        """
        Какие даты у каждого слота уже заняты занятиями.

        Это замена курсора по последнему занятию. Старый генератор брал
        последнее занятие шаблона и прибавлял неделю, из-за чего любая
        дырка в истории (удалённое занятие, изменённый день недели)
        приводила либо к дублям, либо к пропускам.

        Здесь мы просто спрашиваем факт: что уже есть. Генератор вычитает
        это множество из целевого и создаёт разницу.

        Отменённые занятия ВКЛЮЧЕНЫ в результат намеренно: дата, на которую
        занятие было создано и затем отменено, считается обработанной.
        Иначе следующая генерация воскрешала бы то, что админ только что
        отменил.
        """
        if not slot_ids:
            return {}

        result = await self.db.execute(
            select(Lesson.recurring_pattern_slot_id, Lesson.lesson_date).where(
                and_(
                    Lesson.recurring_pattern_slot_id.in_(slot_ids),
                    Lesson.lesson_date >= from_date,
                    Lesson.lesson_date <= to_date,
                )
            )
        )

        existing: Dict[int, Set[date]] = {slot_id: set() for slot_id in slot_ids}
        for slot_id, lesson_date in result.all():
            if slot_id is not None:
                existing.setdefault(slot_id, set()).add(lesson_date)

        return existing

    async def insert_lessons(self, rows: List[dict]) -> List[InsertedRow]:
        """
        Вставить пачку занятий, пропуская уже существующие.

        Стратегия в два эшелона:

        1. Одним запросом с ON CONFLICT DO NOTHING по уникальному ключу
           (recurring_pattern_slot_id, lesson_date). Дубли отсеиваются базой.

        2. Если запрос упал на IntegrityError - это сработал EXCLUDE-констрейнт
           (кабинет или преподаватель заняты). ON CONFLICT с ним не работает,
           поэтому падает вся пачка целиком. Тогда откатываемся к savepoint'у
           и вставляем построчно: каждая строка в своём savepoint'е, упавшие
           пропускаются, остальные сохраняются.

        Второй эшелон - редкий путь. Конфликты отсеиваются заранее через
        ConflictService, сюда доходят только гонки: кто-то занял кабинет
        между проверкой и вставкой.

        Returns:
            Список (lesson_id, slot_id, lesson_date) фактически созданных.
        """
        if not rows:
            return []

        try:
            async with self.db.begin_nested():
                return await self._bulk_insert(rows)
        except IntegrityError as exc:
            logger.warning(
                "Bulk lesson insert hit a constraint, falling back to row-by-row: %s",
                exc,
            )

        return await self._insert_row_by_row(rows)

    async def _bulk_insert(self, rows: List[dict]) -> List[InsertedRow]:
        """Одна вставка на всю пачку."""
        stmt = (
            pg_insert(Lesson)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_lesson_slot_date")
            .returning(
                Lesson.id,
                Lesson.recurring_pattern_slot_id,
                Lesson.lesson_date,
            )
        )

        result = await self.db.execute(stmt)
        return [tuple(row) for row in result.all()]

    async def _insert_row_by_row(self, rows: List[dict]) -> List[InsertedRow]:
        """
        Построчная вставка с изоляцией каждой строки savepoint'ом.

        Нужна, чтобы одна конфликтная строка не убивала всю генерацию.
        Медленнее пакетной, но выполняется только после её падения.
        """
        inserted: List[InsertedRow] = []

        for row in rows:
            try:
                async with self.db.begin_nested():
                    stmt = (
                        pg_insert(Lesson)
                        .values([row])
                        .on_conflict_do_nothing(constraint="uq_lesson_slot_date")
                        .returning(
                            Lesson.id,
                            Lesson.recurring_pattern_slot_id,
                            Lesson.lesson_date,
                        )
                    )
                    result = await self.db.execute(stmt)
                    inserted.extend(tuple(r) for r in result.all())
            except IntegrityError as exc:
                logger.info(
                    "Lesson skipped on %s (slot %s): %s",
                    row.get("lesson_date"),
                    row.get("recurring_pattern_slot_id"),
                    exc.orig if hasattr(exc, "orig") else exc,
                )

        return inserted

    async def insert_lesson_students(
        self,
        pairs: Iterable[Tuple[int, int]],
    ) -> int:
        """
        Привязать учеников к созданным занятиям.

        Args:
            pairs: последовательность (lesson_id, student_id).

        Дубли гасятся ограничением uq_lesson_student, поэтому повторный
        вызов безопасен.
        """
        rows = [
            {
                "lesson_id": lesson_id,
                "student_id": student_id,
                "attendance_status": "scheduled",
            }
            for lesson_id, student_id in pairs
        ]

        if not rows:
            return 0

        stmt = (
            pg_insert(LessonStudent)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_lesson_student")
        )

        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount or 0

    async def delete_generation_batch(
        self,
        batch_id: UUID,
        not_before: date,
    ) -> List[int]:
        """
        Откатить один прогон генерации.

        Удаляются только занятия, которые:
            - принадлежат этому прогону;
            - лежат не раньше not_before (обычно - сегодня);
            - не правились вручную;
            - находятся в статусе scheduled.

        Прошлое, проведённые занятия и всё, что админ трогал руками,
        остаётся нетронутым. Именно это делает откат безопасным: он не
        может стереть ничего, кроме того, что сам же и создал.

        Returns:
            ID удалённых занятий, а не их количество. Удаление - такой же
            факт, как создание, и рассказать о нём аналитической проекции
            нужно поимённо: иначе она навсегда останется со строками
            о занятиях, которых больше нет.
        """
        result = await self.db.execute(
            delete(Lesson)
            .where(
                and_(
                    Lesson.generation_batch_id == batch_id,
                    Lesson.lesson_date >= not_before,
                    Lesson.is_manually_modified.is_(False),
                    Lesson.status == "scheduled",
                )
            )
            .returning(Lesson.id)
            .execution_options(synchronize_session=False)
        )
        deleted_ids = list(result.scalars().all())
        await self.db.flush()

        logger.info(
            "Rolled back generation batch %s: %s lessons deleted",
            batch_id,
            len(deleted_ids),
        )
        return deleted_ids

    async def delete_future_lessons_for_slots(
        self,
        slot_ids: Sequence[int],
        not_before: date,
    ) -> List[int]:
        """
        Удалить будущие несостоявшиеся занятия указанных слотов.

        Используется при удалении слота из шаблона, при смене расписания
        шаблона и при удалении шаблона целиком. Условия те же, что
        у отката: прошлое и ручные правки неприкосновенны.

        Returns:
            ID удалённых занятий.
        """
        if not slot_ids:
            return []

        result = await self.db.execute(
            delete(Lesson)
            .where(
                and_(
                    Lesson.recurring_pattern_slot_id.in_(slot_ids),
                    Lesson.lesson_date >= not_before,
                    Lesson.is_manually_modified.is_(False),
                    Lesson.status == "scheduled",
                )
            )
            .returning(Lesson.id)
            .execution_options(synchronize_session=False)
        )
        deleted_ids = list(result.scalars().all())
        await self.db.flush()

        return deleted_ids

    async def count_lessons_for_pattern(
        self,
        pattern_id: int,
        from_date: Optional[date] = None,
    ) -> int:
        """Сколько занятий сгенерировано из шаблона."""
        from sqlalchemy import func

        query = select(func.count(Lesson.id)).where(
            Lesson.recurring_pattern_id == pattern_id
        )

        if from_date:
            query = query.where(Lesson.lesson_date >= from_date)

        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_lesson_ids_for_pattern(
        self,
        pattern_id: int,
        not_before: Optional[date] = None,
    ) -> List[int]:
        """
        ID занятий шаблона.

        Нужен предпросмотру правки: собственные занятия редактируемого
        шаблона не должны считаться конфликтом. При сохранении они будут
        удалены и созданы заново, поэтому показывать их как занятое время
        значит обещать проблему, которой не будет.
        """
        query = select(Lesson.id).where(Lesson.recurring_pattern_id == pattern_id)

        if not_before:
            query = query.where(Lesson.lesson_date >= not_before)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_future_scheduled_lesson_ids(
        self,
        pattern_id: int,
        not_before: date,
    ) -> List[int]:
        """
        ID будущих запланированных занятий шаблона.

        Отличие от get_lesson_ids_for_pattern - фильтр по статусу, и оно
        принципиальное. Тот метод отдаёт все занятия шаблона, чтобы
        исключить их из проверки конфликтов. Здесь же нужны только те,
        у которых состав участников ещё можно менять: проведённое,
        отменённое или пропущенное занятие - это факт с зафиксированной
        посещаемостью, и переписывать его список учеников значит
        подделывать историю.
        """
        result = await self.db.execute(
            select(Lesson.id).where(
                and_(
                    Lesson.recurring_pattern_id == pattern_id,
                    Lesson.lesson_date >= not_before,
                    Lesson.status == "scheduled",
                )
            )
        )
        return list(result.scalars().all())

    async def get_future_scheduled_lesson_dates(
        self,
        pattern_id: int,
        not_before: date,
        limit: int = 5,
    ) -> List[date]:
        """
        Ближайшие даты будущих занятий шаблона.

        Нужны сообщению ученику: одного «занятия по вторникам» мало,
        человеку нужен ориентир «первое - третьего сентября».

        Даты берутся из БД, а не из результата генерации, намеренно.
        При правке одного лишь состава учеников генерация не запускается
        вовсе, но занятия у шаблона есть, и назвать их надо. Опираться
        на то, что создал текущий прогон, значит промолчать ровно в том
        случае, когда сообщение и нужно.
        """
        result = await self.db.execute(
            select(Lesson.lesson_date)
            .where(
                and_(
                    Lesson.recurring_pattern_id == pattern_id,
                    Lesson.lesson_date >= not_before,
                    Lesson.status == "scheduled",
                )
            )
            .distinct()
            .order_by(Lesson.lesson_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_lesson_students(
        self,
        lesson_ids: Sequence[int],
        student_ids: Sequence[int],
    ) -> int:
        """
        Отвязать учеников от занятий.

        Обратная операция к insert_lesson_students. Нужна, когда ученика
        убрали из шаблона: его будущие занятия должны перестать быть
        его занятиями.
        """
        if not lesson_ids or not student_ids:
            return 0

        result = await self.db.execute(
            delete(LessonStudent).where(
                and_(
                    LessonStudent.lesson_id.in_(lesson_ids),
                    LessonStudent.student_id.in_(student_ids),
                )
            )
        )
        await self.db.flush()
        return result.rowcount or 0