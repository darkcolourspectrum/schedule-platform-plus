"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create recurring_patterns table
    op.create_table(
        'recurring_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column('day_of_week', sa.Integer(), nullable=False, comment='1=Понедельник, 2=Вторник, ..., 7=Воскресенье'),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='60', comment='Длительность занятия в минутах'),
        sa.Column('valid_from', sa.Date(), nullable=False, comment='С какой даты начинает действовать шаблон'),
        sa.Column('valid_until', sa.Date(), nullable=True, comment='До какой даты действует (NULL = бессрочно)'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='Активен ли шаблон'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_recurring_patterns_studio_id', 'recurring_patterns', ['studio_id'])
    op.create_index('ix_recurring_patterns_teacher_id', 'recurring_patterns', ['teacher_id'])
    
    # Create lessons table
    op.create_table(
        'lessons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column('recurring_pattern_id', sa.Integer(), nullable=True, comment='NULL = разовое занятие, иначе - сгенерировано из шаблона'),
        sa.Column('lesson_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='scheduled', comment='scheduled, completed, cancelled, missed'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Заметки преподавателя'),
        sa.Column('cancellation_reason', sa.Text(), nullable=True, comment='Причина отмены'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['recurring_pattern_id'], ['recurring_patterns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_studio_date', 'lessons', ['studio_id', 'lesson_date'])
    op.create_index('idx_teacher_date', 'lessons', ['teacher_id', 'lesson_date'])
    op.create_index('idx_classroom_datetime', 'lessons', ['classroom_id', 'lesson_date', 'start_time'])
    op.create_index('idx_status', 'lessons', ['status'])
    
    # Create lesson_students table
    op.create_table(
        'lesson_students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lesson_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('attendance_status', sa.String(20), nullable=False, server_default='scheduled', comment='scheduled, attended, missed, cancelled'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lesson_id', 'student_id', name='uq_lesson_student')
    )
    op.create_index('ix_lesson_students_lesson_id', 'lesson_students', ['lesson_id'])
    op.create_index('ix_lesson_students_student_id', 'lesson_students', ['student_id'])
    
    # Create recurring_pattern_students table
    op.create_table(
        'recurring_pattern_students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recurring_pattern_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['recurring_pattern_id'], ['recurring_patterns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recurring_pattern_id', 'student_id', name='uq_pattern_student')
    )
    op.create_index('ix_recurring_pattern_students_pattern_id', 'recurring_pattern_students', ['recurring_pattern_id'])
    op.create_index('ix_recurring_pattern_students_student_id', 'recurring_pattern_students', ['student_id'])


def downgrade() -> None:
    op.drop_table('recurring_pattern_students')
    op.drop_table('lesson_students')
    op.drop_table('lessons')
    op.drop_table('recurring_patterns')
