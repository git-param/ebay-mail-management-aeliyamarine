"""internal note edit delete search

Revision ID: 20260825_0051
Revises: 20260823_0050
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260825_0051'
down_revision = '20260823_0050'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversation_notes', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversation_notes', sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_conversation_notes_deleted_by_users',
        'conversation_notes',
        'users',
        ['deleted_by'],
        ['id'],
    )
    op.create_index('ix_conversation_notes_active_conversation', 'conversation_notes', ['conversation_id'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_conversation_notes_deleted_by', 'conversation_notes', ['deleted_by'], unique=False)
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_index('ix_messages_body_trgm', 'messages', ['body'], unique=False, postgresql_using='gin', postgresql_ops={'body': 'gin_trgm_ops'})
    op.create_index(
        'ix_conversation_notes_body_active_trgm',
        'conversation_notes',
        ['body'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'body': 'gin_trgm_ops'},
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_conversation_notes_body_active_trgm', table_name='conversation_notes')
    op.drop_index('ix_messages_body_trgm', table_name='messages')
    op.drop_index('ix_conversation_notes_deleted_by', table_name='conversation_notes')
    op.drop_index('ix_conversation_notes_active_conversation', table_name='conversation_notes')
    op.drop_constraint('fk_conversation_notes_deleted_by_users', 'conversation_notes', type_='foreignkey')
    op.drop_column('conversation_notes', 'deleted_by')
    op.drop_column('conversation_notes', 'deleted_at')
