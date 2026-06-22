"""Add local storage path for reply attachments.

Revision ID: 20260622_0016
Revises: 20260622_0015
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260622_0016'
down_revision = '20260622_0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add local file path metadata for uploaded reply attachments."""
    op.add_column('message_attachments', sa.Column('storage_path', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove local file path metadata for uploaded reply attachments."""
    op.drop_column('message_attachments', 'storage_path')
