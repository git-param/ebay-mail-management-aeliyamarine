"""create ebay api usage

Revision ID: 20260620_0013
Revises: dccd15e43977
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260620_0013'
down_revision = 'dccd15e43977'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ebay_api_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('usage_date', sa.Date(), nullable=False),
        sa.Column('call_count', sa.Integer(), nullable=False),
        sa.Column('daily_limit', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usage_date', name='uq_ebay_api_usage_date'),
    )
    op.create_index('ix_ebay_api_usage_usage_date', 'ebay_api_usage', ['usage_date'])


def downgrade() -> None:
    op.drop_index('ix_ebay_api_usage_usage_date', table_name='ebay_api_usage')
    op.drop_table('ebay_api_usage')
