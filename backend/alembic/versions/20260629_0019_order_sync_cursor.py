"""add order synchronization cursor and external order timestamps

Revision ID: 20260629_0019
Revises: 20260624_0018
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = '20260629_0019'
down_revision = '20260624_0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ebay_accounts', sa.Column('last_order_sync_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('external_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('external_last_modified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_orders_account_external_created_at', 'orders', ['account_id', 'external_created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_orders_account_external_created_at', table_name='orders')
    op.drop_column('orders', 'external_last_modified_at')
    op.drop_column('orders', 'external_created_at')
    op.drop_column('ebay_accounts', 'last_order_sync_at')
