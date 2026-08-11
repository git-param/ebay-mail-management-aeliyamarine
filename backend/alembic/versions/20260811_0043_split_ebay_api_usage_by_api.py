"""split ebay api usage by api

Revision ID: 20260811_0043
Revises: 17431a2f681a
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260811_0043'
down_revision = '17431a2f681a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ebay_api_usage',
        sa.Column('api_name', sa.String(length=80), nullable=False, server_default='commerce'),
    )
    op.drop_constraint('uq_ebay_api_usage_date', 'ebay_api_usage', type_='unique')
    op.create_unique_constraint('uq_ebay_api_usage_date_api_name', 'ebay_api_usage', ['usage_date', 'api_name'])
    op.create_index('ix_ebay_api_usage_api_name', 'ebay_api_usage', ['api_name'])
    op.alter_column('ebay_api_usage', 'api_name', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_ebay_api_usage_api_name', table_name='ebay_api_usage')
    op.drop_constraint('uq_ebay_api_usage_date_api_name', 'ebay_api_usage', type_='unique')
    op.create_unique_constraint('uq_ebay_api_usage_date', 'ebay_api_usage', ['usage_date'])
    op.drop_column('ebay_api_usage', 'api_name')
