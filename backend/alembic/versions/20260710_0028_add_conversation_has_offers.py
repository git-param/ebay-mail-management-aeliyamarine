"""add conversation has_offers flag

Revision ID: 20260710_0028
Revises: f3d5c50fa008
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260710_0028'
down_revision = 'f3d5c50fa008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('has_offers', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE conversations
        SET has_offers = EXISTS (
            SELECT 1 FROM offers WHERE offers.conversation_id = conversations.id
        )
        """
    )


def downgrade() -> None:
    op.drop_column('conversations', 'has_offers')
