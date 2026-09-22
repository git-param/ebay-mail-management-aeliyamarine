"""Add indexes for inbox, SLA, assignment, and daily-entry queries.

Revision ID: 20260921_0058
Revises: 20260919_0057
Create Date: 2026-09-21 00:00:00.000000
"""

from alembic import op


revision = '20260921_0058'
down_revision = '20260919_0057'
branch_labels = None
depends_on = None


INDEXES = {
    'ix_conversations_linked_order': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_linked_order '
        'ON conversations (linked_order_record_id)'
    ),
    'ix_coc_order_record': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_coc_order_record '
        'ON conversation_order_contexts (order_record_id)'
    ),
    'ix_oli_order_record': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_oli_order_record '
        'ON order_line_items (order_record_id)'
    ),
    'ix_oli_account_item': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_oli_account_item '
        'ON order_line_items (account_id, item_id)'
    ),
    'ix_oli_account_listing': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_oli_account_listing '
        'ON order_line_items (account_id, listing_id)'
    ),
    'ix_coc_ebay_order_id_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_coc_ebay_order_id_trgm '
        'ON conversation_order_contexts USING gin (ebay_order_id gin_trgm_ops)'
    ),
    'ix_coc_legacy_order_id_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_coc_legacy_order_id_trgm '
        'ON conversation_order_contexts USING gin (legacy_order_id gin_trgm_ops)'
    ),
    'ix_coc_sku_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_coc_sku_trgm '
        'ON conversation_order_contexts USING gin (sku gin_trgm_ops)'
    ),
    'ix_coc_inventory_id_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_coc_inventory_id_trgm '
        'ON conversation_order_contexts USING gin (inventory_id gin_trgm_ops)'
    ),
    'ix_cpc_order_id_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cpc_order_id_trgm '
        'ON conversation_product_contexts USING gin (order_id gin_trgm_ops)'
    ),
    'ix_cpc_sku_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cpc_sku_trgm '
        'ON conversation_product_contexts USING gin (sku gin_trgm_ops)'
    ),
    'ix_orders_order_id_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_order_id_trgm '
        'ON orders USING gin (order_id gin_trgm_ops)'
    ),
    'ix_oli_order_id_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_oli_order_id_trgm '
        'ON order_line_items USING gin (order_id gin_trgm_ops)'
    ),
    'ix_oli_sku_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_oli_sku_trgm '
        'ON order_line_items USING gin (sku gin_trgm_ops)'
    ),
    'ix_conversations_inbox_activity': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_inbox_activity '
        'ON conversations (last_message_at DESC, created_at DESC)'
    ),
    'ix_conversations_status_activity': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_status_activity '
        'ON conversations (status, last_message_at DESC)'
    ),
    'ix_conversations_account_activity': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_account_activity '
        'ON conversations (provider_account_id, last_message_at DESC)'
    ),
    'ix_conversations_category_activity': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_category_activity '
        'ON conversations (category_id, last_message_at DESC)'
    ),
    'ix_conversations_type_activity': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_type_activity '
        'ON conversations (provider_conversation_type, last_message_at DESC)'
    ),
    'ix_conversations_buyer_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_buyer_trgm '
        'ON conversations USING gin (buyer_identifier gin_trgm_ops)'
    ),
    'ix_conversations_subject_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_subject_trgm '
        'ON conversations USING gin (subject gin_trgm_ops)'
    ),
    'ix_conversations_reference_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_reference_trgm '
        'ON conversations USING gin (reference_id gin_trgm_ops)'
    ),
    'ix_messages_conversation_sent': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_messages_conversation_sent '
        'ON messages (conversation_id, sent_at)'
    ),
    'ix_messages_body_trgm': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_messages_body_trgm '
        'ON messages USING gin (body gin_trgm_ops)'
    ),
    'ix_conversation_assignments_active_conversation': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversation_assignments_active_conversation '
        'ON conversation_assignments (conversation_id, assigned_at DESC) '
        'WHERE unassigned_at IS NULL'
    ),
    'ix_conversation_assignments_active_user': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversation_assignments_active_user '
        'ON conversation_assignments (assigned_to, conversation_id) '
        'WHERE unassigned_at IS NULL'
    ),
    'ix_sla_history_active_conversation': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sla_history_active_conversation '
        'ON conversation_sla_history (conversation_id, cycle_number DESC) '
        'WHERE replied_time IS NULL'
    ),
    'ix_sla_history_replier_time': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sla_history_replier_time '
        'ON conversation_sla_history (replied_by, replied_time) '
        'WHERE sla_met IS NOT NULL'
    ),
    'ix_daily_entries_date_created': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_daily_entries_date_created '
        'ON daily_task_entries (entry_date DESC, created_at DESC)'
    ),
    'ix_daily_entry_history_entry_changed': (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_daily_entry_history_entry_changed '
        'ON daily_task_entry_history (entry_id, changed_at DESC)'
    ),
}


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    with op.get_context().autocommit_block():
        for statement in INDEXES.values():
            op.execute(statement)


def downgrade() -> None:
    for index_name in reversed(INDEXES):
        op.execute(f'DROP INDEX IF EXISTS {index_name}')
