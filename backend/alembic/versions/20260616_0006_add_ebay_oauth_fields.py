"""add ebay oauth fields

Revision ID: 20260616_0006
Revises: 20260616_0005
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa


revision = '20260616_0006'
down_revision = '20260616_0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE ebay_connection_status ADD VALUE IF NOT EXISTS 'PENDING'")
    op.execute("ALTER TYPE ebay_connection_status ADD VALUE IF NOT EXISTS 'FAILED'")

    op.add_column('ebay_accounts', sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ebay_accounts', sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ebay_accounts', sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_ebay_accounts_oauth_state'), 'ebay_accounts', ['oauth_state'], unique=False)

    op.execute("UPDATE ebay_accounts SET access_token_expires_at = token_expires_at WHERE token_expires_at IS NOT NULL")


def downgrade() -> None:
    op.drop_index(op.f('ix_ebay_accounts_oauth_state'), table_name='ebay_accounts')
    op.drop_column('ebay_accounts', 'last_connected_at')
    op.drop_column('ebay_accounts', 'refresh_token_expires_at')
    op.drop_column('ebay_accounts', 'access_token_expires_at')
