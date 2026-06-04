"""add analytics projections: lead_facts, lead_status_transitions, lesson_facts

Revision ID: 7d4e9a1c5b2f
Revises: 3a1f7c2b9e84
Create Date: 2026-06-04 10:00:00.000000

Аналитическая read-модель для админского дашборда. Наполняется
consumer'ами событий CRM ('crm_events') и Schedule ('schedule_events').
Backfill существующих данных - отдельным скриптом после применения.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '7d4e9a1c5b2f'
down_revision = '3a1f7c2b9e84'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- lead_facts: текущее состояние лида ----------
    op.create_table(
        'lead_facts',
        sa.Column('id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('current_status', sa.String(length=32), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('lost_reason', sa.String(length=500), nullable=True),
        sa.Column('converted_user_id', sa.Integer(), nullable=True),
        sa.Column(
            'is_converted',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column('lead_created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='occurred_at последнего применённого события',
        ),
        sa.Column(
            'synced_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Когда запись впервые появилась в lead_facts',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_lead_facts_source'), 'lead_facts', ['source'], unique=False
    )
    op.create_index(
        op.f('ix_lead_facts_current_status'),
        'lead_facts',
        ['current_status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lead_facts_studio_id'),
        'lead_facts',
        ['studio_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lead_facts_lead_created_at'),
        'lead_facts',
        ['lead_created_at'],
        unique=False,
    )
    op.create_index(
        'ix_lead_facts_status_created',
        'lead_facts',
        ['current_status', 'lead_created_at'],
        unique=False,
    )
    op.create_index(
        'ix_lead_facts_source_created',
        'lead_facts',
        ['source', 'lead_created_at'],
        unique=False,
    )

    # ---------- lead_status_transitions: лог переходов (append-only) ----------
    op.create_table(
        'lead_status_transitions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.BigInteger(), nullable=False),
        sa.Column('from_status', sa.String(length=32), nullable=True),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('studio_id', sa.Integer(), nullable=True),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'source_event_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_event_id'),
    )
    op.create_index(
        op.f('ix_lead_status_transitions_lead_id'),
        'lead_status_transitions',
        ['lead_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lead_status_transitions_to_status'),
        'lead_status_transitions',
        ['to_status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lead_status_transitions_occurred_at'),
        'lead_status_transitions',
        ['occurred_at'],
        unique=False,
    )
    op.create_index(
        'ix_lead_transitions_to_status_time',
        'lead_status_transitions',
        ['to_status', 'occurred_at'],
        unique=False,
    )
    op.create_index(
        'ix_lead_transitions_lead_time',
        'lead_status_transitions',
        ['lead_id', 'occurred_at'],
        unique=False,
    )

    # ---------- lesson_facts: проекция занятий ----------
    op.create_table(
        'lesson_facts',
        sa.Column('id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('teacher_id', sa.BigInteger(), nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('classroom_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('lesson_date', sa.Date(), nullable=False),
        sa.Column(
            'student_count',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'rescheduled_count',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('cancellation_reason', sa.String(length=1000), nullable=True),
        sa.Column('lesson_created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='occurred_at последнего применённого события',
        ),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_lesson_facts_teacher_id'),
        'lesson_facts',
        ['teacher_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lesson_facts_studio_id'),
        'lesson_facts',
        ['studio_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lesson_facts_status'),
        'lesson_facts',
        ['status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_lesson_facts_lesson_date'),
        'lesson_facts',
        ['lesson_date'],
        unique=False,
    )
    op.create_index(
        'ix_lesson_facts_teacher_date',
        'lesson_facts',
        ['teacher_id', 'lesson_date'],
        unique=False,
    )
    op.create_index(
        'ix_lesson_facts_studio_status_date',
        'lesson_facts',
        ['studio_id', 'status', 'lesson_date'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_lesson_facts_studio_status_date', table_name='lesson_facts'
    )
    op.drop_index('ix_lesson_facts_teacher_date', table_name='lesson_facts')
    op.drop_index(op.f('ix_lesson_facts_lesson_date'), table_name='lesson_facts')
    op.drop_index(op.f('ix_lesson_facts_status'), table_name='lesson_facts')
    op.drop_index(op.f('ix_lesson_facts_studio_id'), table_name='lesson_facts')
    op.drop_index(op.f('ix_lesson_facts_teacher_id'), table_name='lesson_facts')
    op.drop_table('lesson_facts')

    op.drop_index(
        'ix_lead_transitions_lead_time', table_name='lead_status_transitions'
    )
    op.drop_index(
        'ix_lead_transitions_to_status_time',
        table_name='lead_status_transitions',
    )
    op.drop_index(
        op.f('ix_lead_status_transitions_occurred_at'),
        table_name='lead_status_transitions',
    )
    op.drop_index(
        op.f('ix_lead_status_transitions_to_status'),
        table_name='lead_status_transitions',
    )
    op.drop_index(
        op.f('ix_lead_status_transitions_lead_id'),
        table_name='lead_status_transitions',
    )
    op.drop_table('lead_status_transitions')

    op.drop_index('ix_lead_facts_source_created', table_name='lead_facts')
    op.drop_index('ix_lead_facts_status_created', table_name='lead_facts')
    op.drop_index(
        op.f('ix_lead_facts_lead_created_at'), table_name='lead_facts'
    )
    op.drop_index(op.f('ix_lead_facts_studio_id'), table_name='lead_facts')
    op.drop_index(
        op.f('ix_lead_facts_current_status'), table_name='lead_facts'
    )
    op.drop_index(op.f('ix_lead_facts_source'), table_name='lead_facts')
    op.drop_table('lead_facts')