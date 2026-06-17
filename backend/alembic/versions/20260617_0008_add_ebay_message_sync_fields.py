"""add ebay message sync fields

Revision ID: 20260617_0008
Revises: fba04a28d0a8
Create Date: 2026-06-17

"""
from alembic import op
import sqlalchemy as sa


revision = '20260617_0008'
down_revision = 'fba04a28d0a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('provider_conversation_status', sa.String(length=50), nullable=True))
    op.add_column('conversations', sa.Column('provider_conversation_type', sa.String(length=50), nullable=True))
    op.add_column('conversations', sa.Column('reference_id', sa.String(length=255), nullable=True))
    op.add_column('conversations', sa.Column('reference_type', sa.String(length=50), nullable=True))
    op.add_column('conversations', sa.Column('unread_count', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('conversations', 'unread_count', server_default=None)
    op.create_index(
        op.f('ix_conversations_provider_conversation_status'),
        'conversations',
        ['provider_conversation_status'],
        unique=False,
    )
    op.create_index(op.f('ix_conversations_reference_id'), 'conversations', ['reference_id'], unique=False)

    op.add_column('messages', sa.Column('recipient_identifier', sa.String(length=255), nullable=True))
    op.add_column('messages', sa.Column('read_status', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'read_status')
    op.drop_column('messages', 'recipient_identifier')

    op.drop_index(op.f('ix_conversations_reference_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_provider_conversation_status'), table_name='conversations')
    op.drop_column('conversations', 'unread_count')
    op.drop_column('conversations', 'reference_type')
    op.drop_column('conversations', 'reference_id')
    op.drop_column('conversations', 'provider_conversation_type')
    op.drop_column('conversations', 'provider_conversation_status')
