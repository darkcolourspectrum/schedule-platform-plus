"""
Фоновое продление горизонта расписания.

Занятия должны существовать не только на сегодня, но и на пару недель
вперёд. Кто-то должен регулярно догенерировать их по активным шаблонам.

Раньше это делал GET-запрос расписания студии: перед выдачей данных
ScheduleService дёргал check_and_generate_if_needed. Последствия были
такие:

    - просмотр расписания оказывался операцией записи;
    - две открытые вкладки запускали две конкурентные генерации;
    - расписание преподавателя и ученика не догенерировало вовсе,
      потому что вызов стоял только в ветке студии;
    - объём работы внутри HTTP-запроса зависел от количества шаблонов.

Здесь всё это уходит. Продление горизонта - фоновая задача, у неё свой
цикл, своя транзакция и своя изоляция от HTTP.

Устройство скопировано с OutboxPublisherWorker, который уже работает
в этом сервисе: asyncio.Task, интервальный опрос, устойчивость к сбоям,
остановка через lifespan.

Изоляция запусков:
    Цикл берёт advisory lock в PostgreSQL. Если сервис поднят в двух
    репликах, генерацию выполнит только одна, вторая тихо пропустит такт.
    Дублей это не создало бы в любом случае - генератор идемпотентен, -
    но лишнюю работу и лишние блокировки строк убирает.

Изоляция шаблонов:
    Каждый шаблон обрабатывается в собственной транзакции. Сломанный
    шаблон не мешает остальным: он логируется и пропускается, следующие
    обрабатываются как ни в чём не бывало.
"""

import asyncio
import logging
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.domain.recurrence import generation_horizon_end, today_in_studio_tz
from app.repositories.conflict_repository import ConflictRepository
from app.repositories.lesson_generation_repository import (
    LessonGenerationRepository,
)
from app.repositories.recurring_pattern_repository import (
    RecurringPatternRepository,
)
from app.services.conflict_service import ConflictService
from app.services.lesson_generator_service import LessonGeneratorService

logger = logging.getLogger(__name__)


# Произвольная константа, общая для всех реплик сервиса. Смысл имеет
# только совпадение значения: две реплики с одним числом не смогут
# одновременно держать блокировку.
GENERATION_ADVISORY_LOCK_KEY = 918273645


class ScheduleGenerationWorker:
    """Периодически догенерирует занятия по активным шаблонам."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: Optional[float] = None,
        initial_delay_seconds: Optional[float] = None,
    ):
        self._session_factory = session_factory
        self._interval = interval_seconds or (
            settings.schedule_generation_interval_minutes * 60
        )
        self._initial_delay = (
            initial_delay_seconds
            if initial_delay_seconds is not None
            else settings.schedule_generation_initial_delay_seconds
        )
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

    async def start(self) -> None:
        """Запустить фоновый цикл. Вызывается из lifespan."""
        if self._task is not None:
            logger.warning("Generation worker already running")
            return

        self._stopping.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Schedule generation worker started: interval=%ss, horizon=%s weeks",
            self._interval,
            settings.schedule_generation_weeks,
        )

    async def stop(self) -> None:
        """Остановить цикл и дождаться завершения текущего такта."""
        if self._task is None:
            return

        self._stopping.set()
        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

        logger.info("Schedule generation worker stopped")

    async def _run(self) -> None:
        """
        Основной цикл.

        Первый такт выполняется с задержкой: при старте сервиса сначала
        должны подняться подключение к БД и consumer'ы, иначе генерация
        поработает по неполному кешу студий и кабинетов.
        """
        try:
            await asyncio.wait_for(
                self._stopping.wait(), timeout=self._initial_delay
            )
            return
        except asyncio.TimeoutError:
            pass

        while not self._stopping.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Цикл не должен умирать от единичного сбоя: упавшая БД
                # поднимется, следующий такт отработает штатно.
                logger.exception("Generation cycle failed: %s", exc)

            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self._interval
                )
            except asyncio.TimeoutError:
                continue

    # ==================== ОДИН ТАКТ ====================

    async def run_once(self) -> Tuple[int, int]:
        """
        Один проход по всем активным шаблонам.

        Вынесен в отдельный публичный метод, чтобы его можно было
        вызвать вручную из скрипта, не поднимая весь цикл.

        Returns:
            (обработано шаблонов, создано занятий).
        """
        async with self._session_factory() as lock_session:
            acquired = await self._try_acquire_lock(lock_session)

            if not acquired:
                logger.debug(
                    "Generation cycle skipped: another instance holds the lock"
                )
                return 0, 0

            try:
                return await self._generate_all()
            finally:
                await self._release_lock(lock_session)

    async def _try_acquire_lock(self, session: AsyncSession) -> bool:
        """
        Попробовать взять advisory lock.

        pg_try_advisory_lock не ждёт: если блокировка занята, сразу
        возвращает false. Для периодической задачи это правильно -
        лучше пропустить такт, чем копить очередь ожидающих.
        """
        result = await session.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": GENERATION_ADVISORY_LOCK_KEY},
        )
        return bool(result.scalar())

    async def _release_lock(self, session: AsyncSession) -> None:
        """Отпустить advisory lock."""
        try:
            await session.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": GENERATION_ADVISORY_LOCK_KEY},
            )
        except Exception as exc:
            # Блокировка сессионного уровня в любом случае снимется при
            # закрытии соединения, поэтому это не критично.
            logger.warning("Failed to release generation lock: %s", exc)

    async def _generate_all(self) -> Tuple[int, int]:
        """Загрузить активные шаблоны и обработать каждый отдельно."""
        today = today_in_studio_tz()
        horizon_end = generation_horizon_end(today)

        patterns = await self._load_active_patterns(today)

        if not patterns:
            logger.debug("No active patterns to generate")
            return 0, 0

        processed = 0
        total_created = 0

        for pattern_data in patterns:
            created = await self._generate_one(pattern_data, horizon_end)
            if created is not None:
                processed += 1
                total_created += created

        logger.info(
            "Generation cycle done: %s/%s patterns processed, "
            "%s lessons created, horizon %s",
            processed,
            len(patterns),
            total_created,
            horizon_end,
        )

        return processed, total_created

    async def _load_active_patterns(self, today: date) -> List[dict]:
        """
        Прочитать активные шаблоны со слотами и учениками.

        Данные забираем в простые словари, а не возим ORM-объекты между
        сессиями. Так исключены сюрпризы с отсоединёнными объектами
        и ленивой подгрузкой связей.
        """
        async with self._session_factory() as session:
            pattern_repo = RecurringPatternRepository(session)
            patterns = await pattern_repo.get_active_patterns_full(
                as_of_date=today
            )

            return [
                {
                    "pattern": pattern,
                    "slots": list(pattern.slots),
                    "student_ids": [
                        link.student_id for link in pattern.students
                    ],
                }
                for pattern in patterns
            ]

    async def _generate_one(
        self,
        pattern_data: dict,
        horizon_end: date,
    ) -> Optional[int]:
        """
        Обработать один шаблон в собственной транзакции.

        Returns:
            Количество созданных занятий, либо None при сбое.
        """
        pattern = pattern_data["pattern"]

        try:
            async with self._session_factory() as session:
                generator = LessonGeneratorService(
                    generation_repo=LessonGenerationRepository(session),
                    conflict_service=ConflictService(
                        ConflictRepository(session)
                    ),
                )

                result = await generator.generate_pattern(
                    pattern=pattern,
                    slots=pattern_data["slots"],
                    student_ids=pattern_data["student_ids"],
                    until_date=horizon_end,
                )

                await session.commit()

                if result.blocked_count:
                    logger.info(
                        "Pattern %s: %s lessons blocked by conflicts",
                        pattern.id,
                        result.blocked_count,
                    )

                return result.created_count

        except Exception as exc:
            # Сломанный шаблон не должен останавливать остальные.
            logger.exception(
                "Failed to generate lessons for pattern %s: %s", pattern.id, exc
            )
            return None


# Глобальный экземпляр, инициализируется в lifespan приложения -
# тот же приём, что у OutboxPublisherWorker.
worker: Optional[ScheduleGenerationWorker] = None


def init_generation_worker(
    session_factory: async_sessionmaker[AsyncSession],
) -> ScheduleGenerationWorker:
    """Инициализация глобального воркера. Вызывается из lifespan main.py."""
    global worker
    if worker is None:
        worker = ScheduleGenerationWorker(session_factory=session_factory)
    return worker