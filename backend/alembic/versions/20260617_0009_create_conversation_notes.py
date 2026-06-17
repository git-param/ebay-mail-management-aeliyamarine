"""create conversation notes

Revision ID: 20260617_0009
Revises: 003557e07eb9
Create Date: 2026-06-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260617_0009'
down_revision = '003557e07eb9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversation_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_conversation_notes_author_id'), 'conversation_notes', ['author_id'], unique=False)
    op.create_index(op.f('ix_conversation_notes_conversation_id'), 'conversation_notes', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_conversation_notes_conversation_id'), table_name='conversation_notes')
    op.drop_index(op.f('ix_conversation_notes_author_id'), table_name='conversation_notes')
    op.drop_table('conversation_notes')
