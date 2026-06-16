"""create conversation foundation

Revision ID: 20260616_0004
Revises: 20260616_0003
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260616_0004'
down_revision = '20260616_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conversation_status_enum = postgresql.ENUM(
        'OPEN',
        'PENDING',
        'RESOLVED',
        'CLOSED',
        name='conversation_status',
        create_type=False,
    )
    message_sender_type_enum = postgresql.ENUM(
        'CUSTOMER',
        'AGENT',
        'SYSTEM',
        'PROVIDER',
        name='message_sender_type',
        create_type=False,
    )
    sync_log_status_enum = postgresql.ENUM(
        'PENDING',
        'RUNNING',
        'SUCCESS',
        'FAILED',
        name='sync_log_status',
        create_type=False,
    )
    conversation_status_enum.create(op.get_bind(), checkfirst=True)
    message_sender_type_enum.create(op.get_bind(), checkfirst=True)
    sync_log_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_conversation_id', sa.String(length=255), nullable=False),
        sa.Column('provider_account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('buyer_identifier', sa.String(length=255), nullable=True),
        sa.Column('status', conversation_status_enum, nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('external_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_conversation_id', name='uq_conversations_provider_external_id'),
    )
    op.create_index(op.f('ix_conversations_category_id'), 'conversations', ['category_id'], unique=False)
    op.create_index(op.f('ix_conversations_provider'), 'conversations', ['provider'], unique=False)
    op.create_index(op.f('ix_conversations_provider_account_id'), 'conversations', ['provider_account_id'], unique=False)
    op.create_index(op.f('ix_conversations_status'), 'conversations', ['status'], unique=False)

    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=False),
        sa.Column('sender_type', message_sender_type_enum, nullable=False),
        sa.Column('sender_identifier', sa.String(length=255), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_inbound', sa.Boolean(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_message_id', name='uq_messages_provider_external_id'),
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_sent_at'), 'messages', ['sent_at'], unique=False)

    op.create_table(
        'conversation_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('unassigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id']),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_conversation_assignments_current',
        'conversation_assignments',
        ['conversation_id'],
        unique=False,
        postgresql_where=sa.text('unassigned_at IS NULL'),
    )
    op.create_index(op.f('ix_conversation_assignments_assigned_to'), 'conversation_assignments', ['assigned_to'], unique=False)

    op.create_table(
        'conversation_status_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('old_status', conversation_status_enum, nullable=True),
        sa.Column('new_status', conversation_status_enum, nullable=False),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_conversation_status_history_conversation_id'),
        'conversation_status_history',
        ['conversation_id'],
        unique=False,
    )

    op.create_table(
        'conversation_category_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('old_category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('new_category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['new_category_id'], ['categories.id']),
        sa.ForeignKeyConstraint(['old_category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_conversation_category_history_conversation_id'),
        'conversation_category_history',
        ['conversation_id'],
        unique=False,
    )

    op.create_table(
        'sync_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sync_type', sa.String(length=80), nullable=False),
        sa.Column('status', sync_log_status_enum, nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('records_processed', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sync_logs_provider'), 'sync_logs', ['provider'], unique=False)
    op.create_index(op.f('ix_sync_logs_provider_account_id'), 'sync_logs', ['provider_account_id'], unique=False)
    op.create_index(op.f('ix_sync_logs_status'), 'sync_logs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sync_logs_status'), table_name='sync_logs')
    op.drop_index(op.f('ix_sync_logs_provider_account_id'), table_name='sync_logs')
    op.drop_index(op.f('ix_sync_logs_provider'), table_name='sync_logs')
    op.drop_table('sync_logs')
    op.drop_index(op.f('ix_conversation_category_history_conversation_id'), table_name='conversation_category_history')
    op.drop_table('conversation_category_history')
    op.drop_index(op.f('ix_conversation_status_history_conversation_id'), table_name='conversation_status_history')
    op.drop_table('conversation_status_history')
    op.drop_index(op.f('ix_conversation_assignments_assigned_to'), table_name='conversation_assignments')
    op.drop_index('ix_conversation_assignments_current', table_name='conversation_assignments')
    op.drop_table('conversation_assignments')
    op.drop_index(op.f('ix_messages_sent_at'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_conversations_status'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_provider_account_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_provider'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_category_id'), table_name='conversations')
    op.drop_table('conversations')
    postgresql.ENUM(name='sync_log_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='message_sender_type').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='conversation_status').drop(op.get_bind(), checkfirst=True)
