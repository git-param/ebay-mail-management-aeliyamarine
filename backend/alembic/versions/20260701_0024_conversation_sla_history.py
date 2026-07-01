"""add immutable conversation SLA history

Revision ID: 20260701_0024
Revises: 20260630_0023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260701_0024'
down_revision = '20260630_0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create indexed SLA-cycle history without modifying existing threads."""
    op.create_table(
        'conversation_sla_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cycle_number', sa.Integer(), nullable=False),
        sa.Column('buyer_message_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('replied_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replied_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('response_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('sla_met', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['replied_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'cycle_number', name='uq_conversation_sla_cycle'),
    )
    for column in ('conversation_id', 'buyer_message_time', 'replied_time', 'replied_by'):
        op.create_index(f'ix_conversation_sla_history_{column}', 'conversation_sla_history', [column])


def downgrade() -> None:
    """Remove SLA-cycle history while leaving conversations untouched."""
    op.drop_table('conversation_sla_history')
