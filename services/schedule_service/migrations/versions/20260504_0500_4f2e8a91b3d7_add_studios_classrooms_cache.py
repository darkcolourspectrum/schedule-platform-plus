"""add studios_cache and classrooms_cache

Revision ID: 4f2e8a91b3d7
Revises: 81123d3ac956
Create Date: 2026-05-04 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4f2e8a91b3d7'
down_revision = '81123d3ac956'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ===== studios_cache =====
    op.create_table(
        'studios_cache',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
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
            comment='Когда запись впервые попала в локальный кеш',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_studios_cache_is_active',
        'studios_cache',
        ['is_active'],
        unique=False,
    )
    
    # ===== classrooms_cache =====
    op.create_table(
        'classrooms_cache',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('studio_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column(
            'capacity',
            sa.Integer(),
            nullable=False,
            server_default='1',
        ),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('equipment', sa.Text(), nullable=True),
        sa.Column('floor', sa.Integer(), nullable=True),
        sa.Column('room_number', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
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
            comment='Когда запись впервые попала в локальный кеш',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_classrooms_cache_studio_id',
        'classrooms_cache',
        ['studio_id'],
        unique=False,
    )
    op.create_index(
        'ix_classrooms_cache_studio_active',
        'classrooms_cache',
        ['studio_id', 'is_active'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_classrooms_cache_studio_active', table_name='classrooms_cache')
    op.drop_index('ix_classrooms_cache_studio_id', table_name='classrooms_cache')
    op.drop_table('classrooms_cache')
    
    op.drop_index('ix_studios_cache_is_active', table_name='studios_cache')
    op.drop_table('studios_cache')