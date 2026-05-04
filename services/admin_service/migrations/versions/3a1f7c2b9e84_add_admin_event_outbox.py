"""add_admin_event_outbox

Revision ID: 3a1f7c2b9e84
Revises: 2ac6ec72a60e
Create Date: 2026-05-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '3a1f7c2b9e84'
down_revision = '2ac6ec72a60e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'event_outbox',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aggregate_type', sa.String(length=64), nullable=False),
        sa.Column('aggregate_id', sa.String(length=128), nullable=False),
        sa.Column('event_type', sa.String(length=128), nullable=False),
        sa.Column('routing_key', sa.String(length=128), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'published_attempts',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('last_error', sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id'),
    )
    op.create_index(
        op.f('ix_event_outbox_event_id'),
        'event_outbox',
        ['event_id'],
        unique=False,
    )
    # Partial-индекс: воркер ищет только неопубликованные события,
    # такой индекс остаётся компактным даже после миллионов опубликованных строк.
    op.create_index(
        'ix_event_outbox_admin_unpublished',
        'event_outbox',
        ['created_at'],
        unique=False,
        postgresql_where=sa.text('published_at IS NULL'),
    )
    op.create_index(
        'ix_event_outbox_admin_aggregate',
        'event_outbox',
        ['aggregate_type', 'aggregate_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_event_outbox_admin_aggregate', table_name='event_outbox')
    op.drop_index(
        'ix_event_outbox_admin_unpublished',
        table_name='event_outbox',
        postgresql_where=sa.text('published_at IS NULL'),
    )
    op.drop_index(op.f('ix_event_outbox_event_id'), table_name='event_outbox')
    op.drop_table('event_outbox')