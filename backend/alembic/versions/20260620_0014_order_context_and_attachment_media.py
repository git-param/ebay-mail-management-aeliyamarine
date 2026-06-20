"""add order context and attachment media fields

Revision ID: 20260620_0014
Revises: 20260620_0013
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260620_0014'
down_revision = '20260620_0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', sa.String(length=255), nullable=False),
        sa.Column('buyer_username', sa.String(length=255), nullable=True),
        sa.Column('payment_status', sa.String(length=80), nullable=True),
        sa.Column('fulfillment_status', sa.String(length=80), nullable=True),
        sa.Column('cancel_status', sa.String(length=80), nullable=True),
        sa.Column('refund_status', sa.String(length=80), nullable=True),
        sa.Column('pricing_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('refunds', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['ebay_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'order_id', name='uq_orders_account_order_id'),
    )
    op.create_index('ix_orders_account_id', 'orders', ['account_id'])
    op.create_index('ix_orders_buyer_username', 'orders', ['buyer_username'])
    op.create_index('ix_orders_order_id', 'orders', ['order_id'])

    op.create_table(
        'order_line_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', sa.String(length=255), nullable=False),
        sa.Column('line_item_id', sa.String(length=255), nullable=False),
        sa.Column('item_id', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('price_value', sa.Numeric(12, 2), nullable=True),
        sa.Column('price_currency', sa.String(length=10), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['ebay_accounts.id']),
        sa.ForeignKeyConstraint(['order_record_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'order_id', 'line_item_id', name='uq_order_line_items_account_order_line'),
    )
    op.create_index('ix_order_line_items_account_id', 'order_line_items', ['account_id'])
    op.create_index('ix_order_line_items_item_id', 'order_line_items', ['item_id'])
    op.create_index('ix_order_line_items_order_id', 'order_line_items', ['order_id'])

    op.create_table(
        'returns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('order_id', sa.String(length=255), nullable=True),
        sa.Column('return_id', sa.String(length=255), nullable=False),
        sa.Column('return_status', sa.String(length=80), nullable=True),
        sa.Column('return_reason', sa.String(length=255), nullable=True),
        sa.Column('return_state', sa.String(length=80), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['ebay_accounts.id']),
        sa.ForeignKeyConstraint(['order_record_id'], ['orders.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'return_id', name='uq_returns_account_return_id'),
    )
    op.create_index('ix_returns_account_id', 'returns', ['account_id'])
    op.create_index('ix_returns_order_id', 'returns', ['order_id'])
    op.create_index('ix_returns_return_id', 'returns', ['return_id'])

    op.create_table(
        'cancellations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('order_id', sa.String(length=255), nullable=True),
        sa.Column('cancel_id', sa.String(length=255), nullable=False),
        sa.Column('cancel_state', sa.String(length=80), nullable=True),
        sa.Column('cancel_reason', sa.String(length=255), nullable=True),
        sa.Column('requester', sa.String(length=255), nullable=True),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['ebay_accounts.id']),
        sa.ForeignKeyConstraint(['order_record_id'], ['orders.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'cancel_id', name='uq_cancellations_account_cancel_id'),
    )
    op.create_index('ix_cancellations_account_id', 'cancellations', ['account_id'])
    op.create_index('ix_cancellations_cancel_id', 'cancellations', ['cancel_id'])
    op.create_index('ix_cancellations_order_id', 'cancellations', ['order_id'])

    op.add_column('conversations', sa.Column('linked_order_record_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_conversations_linked_order_record_id', 'conversations', 'orders', ['linked_order_record_id'], ['id'])
    op.create_index('ix_conversations_linked_order_record_id', 'conversations', ['linked_order_record_id'])

    op.add_column('message_attachments', sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('message_attachments', sa.Column('media_name', sa.String(length=500), nullable=True))
    op.add_column('message_attachments', sa.Column('media_url', sa.Text(), nullable=True))
    op.add_column('message_attachments', sa.Column('media_type', sa.String(length=80), nullable=True))
    op.create_foreign_key('fk_message_attachments_account_id', 'message_attachments', 'ebay_accounts', ['account_id'], ['id'])
    op.create_index('ix_message_attachments_account_id', 'message_attachments', ['account_id'])
    op.execute(
        """
        UPDATE message_attachments ma
        SET account_id = c.provider_account_id,
            media_name = ma.file_name,
            media_url = ma.download_url
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE ma.message_id = m.id
        """
    )


def downgrade() -> None:
    op.drop_index('ix_message_attachments_account_id', table_name='message_attachments')
    op.drop_constraint('fk_message_attachments_account_id', 'message_attachments', type_='foreignkey')
    op.drop_column('message_attachments', 'media_type')
    op.drop_column('message_attachments', 'media_url')
    op.drop_column('message_attachments', 'media_name')
    op.drop_column('message_attachments', 'account_id')

    op.drop_index('ix_conversations_linked_order_record_id', table_name='conversations')
    op.drop_constraint('fk_conversations_linked_order_record_id', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'linked_order_record_id')

    op.drop_index('ix_cancellations_order_id', table_name='cancellations')
    op.drop_index('ix_cancellations_cancel_id', table_name='cancellations')
    op.drop_index('ix_cancellations_account_id', table_name='cancellations')
    op.drop_table('cancellations')

    op.drop_index('ix_returns_return_id', table_name='returns')
    op.drop_index('ix_returns_order_id', table_name='returns')
    op.drop_index('ix_returns_account_id', table_name='returns')
    op.drop_table('returns')

    op.drop_index('ix_order_line_items_order_id', table_name='order_line_items')
    op.drop_index('ix_order_line_items_item_id', table_name='order_line_items')
    op.drop_index('ix_order_line_items_account_id', table_name='order_line_items')
    op.drop_table('order_line_items')

    op.drop_index('ix_orders_order_id', table_name='orders')
    op.drop_index('ix_orders_buyer_username', table_name='orders')
    op.drop_index('ix_orders_account_id', table_name='orders')
    op.drop_table('orders')
