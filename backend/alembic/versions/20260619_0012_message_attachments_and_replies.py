"""add message attachments

Revision ID: 20260619_0012
Revises: afc485467ba5
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260619_0012'
down_revision = 'afc485467ba5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'message_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_attachment_id', sa.String(length=255), nullable=True),
        sa.Column('file_name', sa.String(length=500), nullable=False),
        sa.Column('mime_type', sa.String(length=120), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('download_url', sa.Text(), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'provider_attachment_id', name='uq_message_attachments_provider_attachment'),
    )
    op.create_index('ix_message_attachments_message_id', 'message_attachments', ['message_id'])
    op.create_index('ix_message_attachments_provider_attachment_id', 'message_attachments', ['provider_attachment_id'])


def downgrade() -> None:
    op.drop_index('ix_message_attachments_provider_attachment_id', table_name='message_attachments')
    op.drop_index('ix_message_attachments_message_id', table_name='message_attachments')
    op.drop_table('message_attachments')
