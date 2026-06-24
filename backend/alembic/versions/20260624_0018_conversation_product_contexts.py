"""create conversation product contexts

Revision ID: 20260624_0018
Revises: 20260624_0017
Create Date: 2026-06-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260624_0018'
down_revision = '20260624_0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversation_product_contexts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reference_id', sa.String(length=255), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=False),
        sa.Column('item_title', sa.String(length=500), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('seller_username', sa.String(length=255), nullable=True),
        sa.Column('item_url', sa.Text(), nullable=True),
        sa.Column('sku', sa.String(length=255), nullable=True),
        sa.Column('order_id', sa.String(length=255), nullable=True),
        sa.Column('enrichment_status', sa.String(length=50), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_enriched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', name='uq_conversation_product_contexts_conversation'),
    )
    op.create_index('ix_conversation_product_contexts_conversation_id', 'conversation_product_contexts', ['conversation_id'])
    op.create_index('ix_conversation_product_contexts_reference_id', 'conversation_product_contexts', ['reference_id'])
    op.create_index('ix_conversation_product_contexts_enrichment_status', 'conversation_product_contexts', ['enrichment_status'])


def downgrade() -> None:
    op.drop_index('ix_conversation_product_contexts_enrichment_status', table_name='conversation_product_contexts')
    op.drop_index('ix_conversation_product_contexts_reference_id', table_name='conversation_product_contexts')
    op.drop_index('ix_conversation_product_contexts_conversation_id', table_name='conversation_product_contexts')
    op.drop_table('conversation_product_contexts')
