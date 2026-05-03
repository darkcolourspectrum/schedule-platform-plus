"""add event_outbox table

Revision ID: 81123d3ac956
Revises: a0dbe1dc41e5
Create Date: 2026-05-02 16:28:15.475345

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '81123d3ac956'
down_revision = 'a0dbe1dc41e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('event_outbox',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('aggregate_type', sa.String(length=64), nullable=False),
        sa.Column('aggregate_id', sa.String(length=128), nullable=False),
        sa.Column('event_type', sa.String(length=128), nullable=False),
        sa.Column('routing_key', sa.String(length=128), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_outbox_event_id'), 'event_outbox', ['event_id'], unique=True)
    op.create_index(
        'ix_event_outbox_unpublished',
        'event_outbox',
        ['created_at'],
        postgresql_where=sa.text('published_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_event_outbox_unpublished', table_name='event_outbox')
    op.drop_index(op.f('ix_event_outbox_event_id'), table_name='event_outbox')
    op.drop_table('event_outbox')
