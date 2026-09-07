"""Статус teacher_missed: занятие сорвано по вине преподавателя

Revision ID: c3f8a1d47b52
Revises: ПОДСТАВИТЬ_ТЕКУЩИЙ_HEAD
Create Date: 2026-09-06

CHECK-констрейнт перечисляет допустимые статусы списком, поэтому
добавление пятого - это миграция, хотя ни одна колонка не меняется.
Тип остаётся String(20), 'teacher_missed' в него влезает.

EXCLUDE-констрейнты не трогаем. Они исключают только отменённые
занятия: отмена освобождает слот заранее, а сорванное занятие уже
прошло, и переиспользовать его время задним числом некому.
"""

from alembic import op

revision = 'c3f8a1d47b52'
down_revision = 'b7c4e2f19a03'
branch_labels = None
depends_on = None

OLD_STATUSES = "'scheduled', 'completed', 'cancelled', 'missed'"
NEW_STATUSES = (
    "'scheduled', 'completed', 'cancelled', 'missed', 'teacher_missed'"
)


def upgrade() -> None:
    op.drop_constraint('ck_lesson_status', 'lessons', type_='check')
    op.create_check_constraint(
        'ck_lesson_status',
        'lessons',
        f"status IN ({NEW_STATUSES})",
    )


def downgrade() -> None:
    # Занятия в новом статусе откатывать некуда. 'missed' повесил бы
    # вину на ученика, поэтому переводим в 'cancelled' - ближайшее
    # по смыслу "занятия не было".
    op.execute(
        "UPDATE lessons SET status = 'cancelled' "
        "WHERE status = 'teacher_missed'"
    )
    op.drop_constraint('ck_lesson_status', 'lessons', type_='check')
    op.create_check_constraint(
        'ck_lesson_status',
        'lessons',
        f"status IN ({OLD_STATUSES})",
    )