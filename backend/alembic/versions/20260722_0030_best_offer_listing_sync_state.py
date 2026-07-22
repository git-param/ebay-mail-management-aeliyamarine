"""add best offer listing sync state

Revision ID: 20260722_0030
Revises: 20260710_0029
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260722_0030'
down_revision = '20260710_0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ebay_best_offer_listing_sync_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_empty_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_offer_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_conversation_activity_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_offer_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['ebay_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'listing_id', name='uq_ebay_best_offer_listing_sync_state'),
    )
    op.create_index('ix_best_offer_state_account_checked', 'ebay_best_offer_listing_sync_states', ['account_id', 'last_checked_at'])
    op.create_index(op.f('ix_ebay_best_offer_listing_sync_states_account_id'), 'ebay_best_offer_listing_sync_states', ['account_id'])
    op.create_index(op.f('ix_ebay_best_offer_listing_sync_states_listing_id'), 'ebay_best_offer_listing_sync_states', ['listing_id'])
    op.create_index('ix_offers_account_listing_buyer', 'offers', ['account_id', 'listing_id', 'buyer_username'])
    op.create_index('ix_offers_conversation_provider_time', 'offers', ['conversation_id', 'created_at_provider', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_offers_conversation_provider_time', table_name='offers')
    op.drop_index('ix_offers_account_listing_buyer', table_name='offers')
    op.drop_index(op.f('ix_ebay_best_offer_listing_sync_states_listing_id'), table_name='ebay_best_offer_listing_sync_states')
    op.drop_index(op.f('ix_ebay_best_offer_listing_sync_states_account_id'), table_name='ebay_best_offer_listing_sync_states')
    op.drop_index('ix_best_offer_state_account_checked', table_name='ebay_best_offer_listing_sync_states')
    op.drop_table('ebay_best_offer_listing_sync_states')
