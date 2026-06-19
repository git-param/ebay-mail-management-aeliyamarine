"""add category access notifications and audit filters

Revision ID: 20260619_0011
Revises: 20260619_0010
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260619_0011'
down_revision = '20260619_0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'category_user_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id']),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('category_id', 'user_id', name='uq_category_user_assignments_category_user'),
    )
    op.create_index('ix_category_user_assignments_category_id', 'category_user_assignments', ['category_id'])
    op.create_index('ix_category_user_assignments_user_id', 'category_user_assignments', ['user_id'])

    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column('event_key', sa.String(length=200), nullable=False),
        sa.Column('resource_type', sa.String(length=80), nullable=True),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'event_key', name='uq_notifications_user_event_key'),
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'is_read', 'created_at'])
    op.create_index('ix_notifications_resource', 'notifications', ['resource_type', 'resource_id'])

    op.add_column('audit_logs', sa.Column('category', sa.String(length=80), nullable=True))
    op.add_column('audit_logs', sa.Column('status', sa.String(length=30), nullable=True))
    op.add_column('audit_logs', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_category', 'audit_logs', ['category'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'])
    op.create_index('ix_audit_logs_status', 'audit_logs', ['status'])
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_status', table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_category', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_column('audit_logs', 'metadata')
    op.drop_column('audit_logs', 'status')
    op.drop_column('audit_logs', 'category')

    op.drop_index('ix_notifications_resource', table_name='notifications')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')

    op.drop_index('ix_category_user_assignments_user_id', table_name='category_user_assignments')
    op.drop_index('ix_category_user_assignments_category_id', table_name='category_user_assignments')
    op.drop_table('category_user_assignments')
