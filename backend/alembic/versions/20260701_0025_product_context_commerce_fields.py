"""add product context commerce fields

Revision ID: 20260701_0025
Revises: 20260701_0024
"""
from alembic import op
import sqlalchemy as sa

revision = '20260701_0025'
down_revision = '20260701_0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversation_product_contexts', sa.Column('price_value', sa.Numeric(12, 2), nullable=True))
    op.add_column('conversation_product_contexts', sa.Column('price_currency', sa.String(10), nullable=True))
    op.add_column('conversation_product_contexts', sa.Column('offer_available', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('conversation_product_contexts', sa.Column('buy_now_available', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('conversation_product_contexts', sa.Column('cta_type', sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column('conversation_product_contexts', 'cta_type')
    op.drop_column('conversation_product_contexts', 'buy_now_available')
    op.drop_column('conversation_product_contexts', 'offer_available')
    op.drop_column('conversation_product_contexts', 'price_currency')
    op.drop_column('conversation_product_contexts', 'price_value')
