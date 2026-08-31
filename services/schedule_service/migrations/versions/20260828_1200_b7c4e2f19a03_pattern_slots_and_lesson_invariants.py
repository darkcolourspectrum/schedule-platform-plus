"""pattern slots and lesson invariants

Revision ID: b7c4e2f19a03
Revises: 4f2e8a91b3d7
Create Date: 2026-08-28 12:00:00.000000

ВНИМАНИЕ: миграция УДАЛЯЕТ все данные расписания.

Таблицы recurring_patterns, recurring_pattern_students, lessons и
lesson_students пересоздаются с нуля в новой форме. Это осознанное
решение: в базе только тестовые данные, а аккуратный перенос старых
шаблонов в модель со слотами обошёлся бы дороже, чем стоят эти данные.

Что меняется:
    1. RecurringPattern теряет day_of_week / start_time / duration_minutes /
       classroom_id - они переезжают в новую таблицу recurring_pattern_slots.
       Один шаблон = один набор учеников и период, много слотов.
    2. RecurringPattern получает week_interval (1 или 2) и anchor_date -
       поддержка повторения раз в две недели.
    3. Lessons получает recurring_pattern_slot_id, is_manually_modified
       и generation_batch_id - служебные поля под идемпотентную генерацию,
       защиту ручных правок и откат прогона генерации.
    4. Инварианты переезжают в БД: уникальность занятия внутри слота,
       корректность интервала, допустимые статусы и два EXCLUDE-констрейнта
       на пересечение по кабинету и по преподавателю.

Требуется расширение btree_gist - оно нужно, чтобы в одном GiST-индексе
уживались обычное равенство (classroom_id, teacher_id) и оператор
пересечения диапазонов (&&). В docker-compose schedule-service ходит в БД
под пользователем postgres, прав на CREATE EXTENSION достаточно.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c4e2f19a03'
down_revision = '4f2e8a91b3d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # ===== СНОС СТАРЫХ ТАБЛИЦ =====
    # Порядок важен: сначала зависимые по FK, потом родительские.
    op.drop_table('lesson_students')
    op.drop_table('recurring_pattern_students')
    op.drop_table('lessons')
    op.drop_table('recurring_patterns')

    # ===== recurring_patterns (шапка) =====
    op.create_table(
        'recurring_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column(
            'valid_from',
            sa.Date(),
            nullable=False,
            comment='С какой даты начинает действовать шаблон',
        ),
        sa.Column(
            'valid_until',
            sa.Date(),
            nullable=True,
            comment='До какой даты действует (NULL = бессрочно)',
        ),
        sa.Column(
            'week_interval',
            sa.Integer(),
            nullable=False,
            server_default='1',
            comment='1 = каждую неделю, 2 = раз в две недели',
        ),
        sa.Column(
            'anchor_date',
            sa.Date(),
            nullable=False,
            comment=(
                'Опорная дата для расчёта чётности недели при week_interval=2. '
                'Фиксируется при создании и не меняется при правке valid_from, '
                'чтобы сдвиг даты начала не переворачивал всю сетку занятий'
            ),
        ),
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default='true',
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            'week_interval IN (1, 2)',
            name='ck_pattern_week_interval',
        ),
        sa.CheckConstraint(
            'valid_until IS NULL OR valid_until >= valid_from',
            name='ck_pattern_valid_range',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_recurring_patterns_studio_id', 'recurring_patterns', ['studio_id']
    )
    op.create_index(
        'ix_recurring_patterns_teacher_id', 'recurring_patterns', ['teacher_id']
    )

    # ===== recurring_pattern_slots (новая таблица) =====
    op.create_table(
        'recurring_pattern_slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recurring_pattern_id', sa.Integer(), nullable=False),
        sa.Column(
            'day_of_week',
            sa.Integer(),
            nullable=False,
            comment='1=Понедельник, 2=Вторник, ..., 7=Воскресенье (ISO)',
        ),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column(
            'duration_minutes',
            sa.Integer(),
            nullable=False,
            server_default='60',
        ),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['recurring_pattern_id'],
            ['recurring_patterns.id'],
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'day_of_week BETWEEN 1 AND 7',
            name='ck_pattern_slot_day_of_week',
        ),
        sa.CheckConstraint(
            'duration_minutes > 0 AND duration_minutes <= 480',
            name='ck_pattern_slot_duration',
        ),
        sa.UniqueConstraint(
            'recurring_pattern_id',
            'day_of_week',
            'start_time',
            name='uq_pattern_slot_day_time',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_pattern_slots_pattern_id',
        'recurring_pattern_slots',
        ['recurring_pattern_id'],
    )

    # ===== recurring_pattern_students (без изменений) =====
    op.create_table(
        'recurring_pattern_students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recurring_pattern_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['recurring_pattern_id'],
            ['recurring_patterns.id'],
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'recurring_pattern_id', 'student_id', name='uq_pattern_student'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_recurring_pattern_students_pattern_id',
        'recurring_pattern_students',
        ['recurring_pattern_id'],
    )
    op.create_index(
        'ix_recurring_pattern_students_student_id',
        'recurring_pattern_students',
        ['student_id'],
    )

    # ===== lessons =====
    op.create_table(
        'lessons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column(
            'recurring_pattern_id',
            sa.Integer(),
            nullable=True,
            comment='NULL = разовое занятие, иначе - сгенерировано из шаблона',
        ),
        sa.Column(
            'recurring_pattern_slot_id',
            sa.Integer(),
            nullable=True,
            comment='Слот, из которого выросло занятие. Держит уникальность',
        ),
        sa.Column('lesson_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='scheduled',
            comment='scheduled, completed, cancelled, missed',
        ),
        sa.Column(
            'is_manually_modified',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment=(
                'Занятие правили вручную (перенос, смена кабинета). '
                'Перегенерация из шаблона такие занятия не трогает'
            ),
        ),
        sa.Column(
            'generation_batch_id',
            sa.UUID(),
            nullable=True,
            comment='ID прогона генерации - по нему работает откат',
        ),
        sa.Column(
            'notes', sa.Text(), nullable=True, comment='Заметки преподавателя'
        ),
        sa.Column(
            'cancellation_reason',
            sa.Text(),
            nullable=True,
            comment='Причина отмены',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['recurring_pattern_id'],
            ['recurring_patterns.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['recurring_pattern_slot_id'],
            ['recurring_pattern_slots.id'],
            ondelete='SET NULL',
        ),
        sa.CheckConstraint(
            'end_time > start_time',
            name='ck_lesson_time_order',
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'missed')",
            name='ck_lesson_status',
        ),
        # Главная защита от дублей генерации. Разовые занятия имеют
        # slot_id = NULL и под ограничение не попадают: в Postgres
        # NULL не равен NULL, поэтому строк с NULL может быть сколько угодно.
        sa.UniqueConstraint(
            'recurring_pattern_slot_id',
            'lesson_date',
            name='uq_lesson_slot_date',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_studio_date', 'lessons', ['studio_id', 'lesson_date'])
    op.create_index('idx_teacher_date', 'lessons', ['teacher_id', 'lesson_date'])
    op.create_index(
        'idx_classroom_datetime',
        'lessons',
        ['classroom_id', 'lesson_date', 'start_time'],
    )
    op.create_index('idx_status', 'lessons', ['status'])
    op.create_index(
        'idx_generation_batch',
        'lessons',
        ['generation_batch_id'],
        postgresql_where=sa.text('generation_batch_id IS NOT NULL'),
    )

    # ===== EXCLUDE-констрейнты на пересечение времени =====
    # tsrange(lesson_date + start_time, lesson_date + end_time) собирает из
    # раздельных колонок даты и времени один временной диапазон. Оператор &&
    # проверяет пересечение. Обе функции IMMUTABLE, поэтому годятся для индекса.
    #
    # Отменённые занятия из проверки исключены: отмена освобождает слот.
    # Проведённые и пропущенные - нет: помещение и время были заняты.
    op.execute(
        """
        ALTER TABLE lessons
        ADD CONSTRAINT excl_lesson_classroom_overlap
        EXCLUDE USING gist (
            classroom_id WITH =,
            tsrange(lesson_date + start_time, lesson_date + end_time) WITH &&
        )
        WHERE (classroom_id IS NOT NULL AND status <> 'cancelled')
        """
    )

    op.execute(
        """
        ALTER TABLE lessons
        ADD CONSTRAINT excl_lesson_teacher_overlap
        EXCLUDE USING gist (
            teacher_id WITH =,
            tsrange(lesson_date + start_time, lesson_date + end_time) WITH &&
        )
        WHERE (status <> 'cancelled')
        """
    )

    # ===== lesson_students (без изменений) =====
    op.create_table(
        'lesson_students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lesson_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column(
            'attendance_status',
            sa.String(20),
            nullable=False,
            server_default='scheduled',
            comment='scheduled, attended, missed, cancelled',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['lesson_id'], ['lessons.id'], ondelete='CASCADE'
        ),
        sa.UniqueConstraint(
            'lesson_id', 'student_id', name='uq_lesson_student'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_lesson_students_lesson_id', 'lesson_students', ['lesson_id']
    )
    op.create_index(
        'ix_lesson_students_student_id', 'lesson_students', ['student_id']
    )


def downgrade() -> None:
    """
    Возврат к структуре 001_initial.

    Данные не восстанавливаются - их и не было при апгрейде.
    Downgrade нужен только для того, чтобы alembic мог откатиться
    до предыдущей ревизии без ошибки.
    """
    op.drop_table('lesson_students')
    op.drop_table('lessons')
    op.drop_table('recurring_pattern_students')
    op.drop_table('recurring_pattern_slots')
    op.drop_table('recurring_patterns')

    op.create_table(
        'recurring_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column(
            'duration_minutes',
            sa.Integer(),
            nullable=False,
            server_default='60',
        ),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column(
            'is_active', sa.Boolean(), nullable=False, server_default='true'
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_recurring_patterns_studio_id', 'recurring_patterns', ['studio_id']
    )
    op.create_index(
        'ix_recurring_patterns_teacher_id', 'recurring_patterns', ['teacher_id']
    )

    op.create_table(
        'lessons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column('recurring_pattern_id', sa.Integer(), nullable=True),
        sa.Column('lesson_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='scheduled',
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['recurring_pattern_id'],
            ['recurring_patterns.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_studio_date', 'lessons', ['studio_id', 'lesson_date'])
    op.create_index('idx_teacher_date', 'lessons', ['teacher_id', 'lesson_date'])
    op.create_index(
        'idx_classroom_datetime',
        'lessons',
        ['classroom_id', 'lesson_date', 'start_time'],
    )
    op.create_index('idx_status', 'lessons', ['status'])

    op.create_table(
        'recurring_pattern_students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recurring_pattern_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['recurring_pattern_id'],
            ['recurring_patterns.id'],
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'recurring_pattern_id', 'student_id', name='uq_pattern_student'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_recurring_pattern_students_pattern_id',
        'recurring_pattern_students',
        ['recurring_pattern_id'],
    )
    op.create_index(
        'ix_recurring_pattern_students_student_id',
        'recurring_pattern_students',
        ['student_id'],
    )

    op.create_table(
        'lesson_students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lesson_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column(
            'attendance_status',
            sa.String(20),
            nullable=False,
            server_default='scheduled',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['lesson_id'], ['lessons.id'], ondelete='CASCADE'
        ),
        sa.UniqueConstraint(
            'lesson_id', 'student_id', name='uq_lesson_student'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_lesson_students_lesson_id', 'lesson_students', ['lesson_id']
    )
    op.create_index(
        'ix_lesson_students_student_id', 'lesson_students', ['student_id']
    )