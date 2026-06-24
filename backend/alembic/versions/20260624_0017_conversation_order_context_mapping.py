"""add conversation order context mapping

Revision ID: 20260624_0017
Revises: 20260622_0016
Create Date: 2026-06-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260624_0017'
down_revision = '20260622_0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('order_line_items', sa.Column('listing_id', sa.String(length=255), nullable=True))
    op.add_column('order_line_items', sa.Column('sku', sa.String(length=255), nullable=True))
    op.add_column('order_line_items', sa.Column('image_url', sa.Text(), nullable=True))
    op.create_index('ix_order_line_items_listing_id', 'order_line_items', ['listing_id'])
    op.create_index('ix_order_line_items_sku', 'order_line_items', ['sku'])

    op.create_table(
        'conversation_order_contexts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ebay_order_id', sa.String(length=255), nullable=True),
        sa.Column('legacy_order_id', sa.String(length=255), nullable=True),
        sa.Column('ebay_item_id', sa.String(length=255), nullable=True),
        sa.Column('listing_id', sa.String(length=255), nullable=True),
        sa.Column('transaction_id', sa.String(length=255), nullable=True),
        sa.Column('external_message_id', sa.String(length=255), nullable=True),
        sa.Column('sku', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('buyer_username', sa.String(length=255), nullable=True),
        sa.Column('inventory_id', sa.String(length=255), nullable=True),
        sa.Column('match_strategy', sa.String(length=80), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('raw_identifiers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sync_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_record_id'], ['orders.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', name='uq_conversation_order_contexts_conversation'),
    )
    op.create_index('ix_conversation_order_contexts_conversation_id', 'conversation_order_contexts', ['conversation_id'])
    op.create_index('ix_conversation_order_contexts_ebay_order_id', 'conversation_order_contexts', ['ebay_order_id'])
    op.create_index('ix_conversation_order_contexts_ebay_item_id', 'conversation_order_contexts', ['ebay_item_id'])
    op.create_index('ix_conversation_order_contexts_listing_id', 'conversation_order_contexts', ['listing_id'])
    op.create_index('ix_conversation_order_contexts_sku', 'conversation_order_contexts', ['sku'])


def downgrade() -> None:
    op.drop_index('ix_conversation_order_contexts_sku', table_name='conversation_order_contexts')
    op.drop_index('ix_conversation_order_contexts_listing_id', table_name='conversation_order_contexts')
    op.drop_index('ix_conversation_order_contexts_ebay_item_id', table_name='conversation_order_contexts')
    op.drop_index('ix_conversation_order_contexts_ebay_order_id', table_name='conversation_order_contexts')
    op.drop_index('ix_conversation_order_contexts_conversation_id', table_name='conversation_order_contexts')
    op.drop_table('conversation_order_contexts')

    op.drop_index('ix_order_line_items_sku', table_name='order_line_items')
    op.drop_index('ix_order_line_items_listing_id', table_name='order_line_items')
    op.drop_column('order_line_items', 'image_url')
    op.drop_column('order_line_items', 'sku')
    op.drop_column('order_line_items', 'listing_id')
