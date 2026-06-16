"""create conversation participants

Revision ID: 20260616_0005
Revises: 20260616_0004
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260616_0005'
down_revision = '20260616_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversation_participants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('participant_identifier', sa.String(length=255), nullable=False),
        sa.Column('participant_name', sa.String(length=255), nullable=True),
        sa.Column('participant_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'conversation_id',
            'participant_identifier',
            'participant_type',
            name='uq_conversation_participants_identity',
        ),
    )
    op.create_index(
        op.f('ix_conversation_participants_conversation_id'),
        'conversation_participants',
        ['conversation_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_conversation_participants_participant_identifier'),
        'conversation_participants',
        ['participant_identifier'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_conversation_participants_participant_identifier'),
        table_name='conversation_participants',
    )
    op.drop_index(op.f('ix_conversation_participants_conversation_id'), table_name='conversation_participants')
    op.drop_table('conversation_participants')
