"""create offer management entries

Revision ID: 20260727_0031
Revises: 20260722_0030
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260727_0031'
down_revision = '20260722_0030'
branch_labels = None
depends_on = None


status_enum = postgresql.ENUM(
    'NEW', 'REVIEWING', 'COUNTEROFFER_SENT', 'AWAITING_BUYER', 'FOLLOW_UP_DUE',
    'AWAITING_PAYMENT', 'SOLD', 'CLOSED_PRICE_NOT_MATCHED', 'CLOSED_NO_RESPONSE',
    'CLOSED_BUYER_PURCHASED_ELSEWHERE', 'CLOSED_OUT_OF_STOCK', 'CANCELLED',
    name='offer_management_status',
)
status_column_enum = postgresql.ENUM(
    'NEW', 'REVIEWING', 'COUNTEROFFER_SENT', 'AWAITING_BUYER', 'FOLLOW_UP_DUE',
    'AWAITING_PAYMENT', 'SOLD', 'CLOSED_PRICE_NOT_MATCHED', 'CLOSED_NO_RESPONSE',
    'CLOSED_BUYER_PURCHASED_ELSEWHERE', 'CLOSED_OUT_OF_STOCK', 'CANCELLED',
    name='offer_management_status',
    create_type=False,
)
outcome_enum = postgresql.ENUM(
    'PENDING', 'CONVERTED_TO_SALE', 'BUYER_REJECTED', 'SELLER_REJECTED',
    'NO_RESPONSE', 'PRICE_NOT_MATCHED', 'BUYER_PURCHASED_ELSEWHERE',
    'OUT_OF_STOCK', 'M2M', 'OTHER',
    name='offer_management_outcome',
)
outcome_column_enum = postgresql.ENUM(
    'PENDING', 'CONVERTED_TO_SALE', 'BUYER_REJECTED', 'SELLER_REJECTED',
    'NO_RESPONSE', 'PRICE_NOT_MATCHED', 'BUYER_PURCHASED_ELSEWHERE',
    'OUT_OF_STOCK', 'M2M', 'OTHER',
    name='offer_management_outcome',
    create_type=False,
)
follow_up_enum = postgresql.ENUM(
    'NOT_SCHEDULED', 'SCHEDULED', 'COMPLETED', 'SKIPPED', 'NOT_REQUIRED',
    name='offer_management_follow_up_status',
)
follow_up_column_enum = postgresql.ENUM(
    'NOT_SCHEDULED', 'SCHEDULED', 'COMPLETED', 'SKIPPED', 'NOT_REQUIRED',
    name='offer_management_follow_up_status',
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    status_enum.create(bind, checkfirst=True)
    outcome_enum.create(bind, checkfirst=True)
    follow_up_enum.create(bind, checkfirst=True)
    op.create_table(
        'offer_management_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entry_number', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('offer_date', sa.Date(), nullable=False),
        sa.Column('ebay_account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ebay_account_name', sa.String(length=255), nullable=False),
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('listing_url', sa.Text(), nullable=True),
        sa.Column('sku', sa.String(length=255), nullable=True),
        sa.Column('product_title', sa.String(length=500), nullable=True),
        sa.Column('condition', sa.String(length=120), nullable=True),
        sa.Column('listing_quantity', sa.Integer(), nullable=True),
        sa.Column('offer_quantity', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='USD'),
        sa.Column('listed_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('revised_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('automated_offer_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('buyer_offer_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('counteroffer_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('final_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('buyer_id', sa.String(length=255), nullable=True),
        sa.Column('status', status_column_enum, nullable=False, server_default='NEW'),
        sa.Column('outcome', outcome_column_enum, nullable=False, server_default='PENDING'),
        sa.Column('is_high_value', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_vip_lead', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('follow_up_1_date', sa.Date(), nullable=True),
        sa.Column('follow_up_1_status', follow_up_column_enum, nullable=False, server_default='NOT_SCHEDULED'),
        sa.Column('follow_up_1_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('follow_up_1_notes', sa.Text(), nullable=True),
        sa.Column('follow_up_2_date', sa.Date(), nullable=True),
        sa.Column('follow_up_2_status', follow_up_column_enum, nullable=False, server_default='NOT_SCHEDULED'),
        sa.Column('follow_up_2_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('follow_up_2_notes', sa.Text(), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('internal_notes', sa.Text(), nullable=True),
        sa.Column('related_conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('related_offer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['ebay_account_id'], ['ebay_accounts.id']),
        sa.ForeignKeyConstraint(['related_conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['related_offer_id'], ['offers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entry_number'),
    )
    for name, cols in {
        'ix_offer_management_entries_listing_id': ['listing_id'],
        'ix_offer_management_entries_sku': ['sku'],
        'ix_offer_management_entries_buyer_id': ['buyer_id'],
        'ix_offer_management_entries_created_by_user_id': ['created_by_user_id'],
        'ix_offer_management_entries_offer_date': ['offer_date'],
        'ix_offer_management_entries_status': ['status'],
        'ix_offer_management_entries_ebay_account_id': ['ebay_account_id'],
        'ix_offer_management_entries_created_at': ['created_at'],
    }.items():
        op.create_index(name, 'offer_management_entries', cols)
    op.create_table(
        'offer_management_entry_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('offer_entry_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('changed_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('previous_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['offer_entry_id'], ['offer_management_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_offer_management_entry_history_entry_id', 'offer_management_entry_history', ['offer_entry_id'])
    op.create_index('ix_offer_management_entry_history_changed_by_user_id', 'offer_management_entry_history', ['changed_by_user_id'])
    op.create_index('ix_offer_management_entry_history_changed_at', 'offer_management_entry_history', ['changed_at'])


def downgrade() -> None:
    op.drop_index('ix_offer_management_entry_history_changed_at', table_name='offer_management_entry_history')
    op.drop_index('ix_offer_management_entry_history_changed_by_user_id', table_name='offer_management_entry_history')
    op.drop_index('ix_offer_management_entry_history_entry_id', table_name='offer_management_entry_history')
    op.drop_table('offer_management_entry_history')
    for name in [
        'ix_offer_management_entries_created_at', 'ix_offer_management_entries_ebay_account_id',
        'ix_offer_management_entries_status', 'ix_offer_management_entries_offer_date',
        'ix_offer_management_entries_created_by_user_id', 'ix_offer_management_entries_buyer_id',
        'ix_offer_management_entries_sku', 'ix_offer_management_entries_listing_id',
    ]:
        op.drop_index(name, table_name='offer_management_entries')
    op.drop_table('offer_management_entries')
    bind = op.get_bind()
    follow_up_enum.drop(bind, checkfirst=True)
    outcome_enum.drop(bind, checkfirst=True)
    status_enum.drop(bind, checkfirst=True)
