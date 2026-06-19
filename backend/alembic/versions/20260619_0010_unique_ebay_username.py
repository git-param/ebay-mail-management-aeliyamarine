"""add unique ebay username index

Revision ID: 20260619_0010
Revises: 20260617_0009
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


revision = '20260619_0010'
down_revision = '20260617_0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_ebay_accounts_ebay_username_lower_unique',
        'ebay_accounts',
        [sa.text('lower(ebay_username)')],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_ebay_accounts_ebay_username_lower_unique', table_name='ebay_accounts')
