"""create persisted seller initiated offers

Revision ID: 20260702_0026
Revises: 20260701_0025
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260702_0026'
down_revision = '20260701_0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    offer_status = postgresql.ENUM(
        'PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED',
        name='offer_status',
        create_type=False,
    )
    offer_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'offers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_offer_id', sa.String(255), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('listing_id', sa.String(255), nullable=False),
        sa.Column('buyer_username', sa.String(255), nullable=True),
        sa.Column('offer_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('status', offer_status, nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_offer_id', name='uq_offers_provider_offer_id'),
    )
    op.create_index('ix_offers_conversation_id', 'offers', ['conversation_id'])
    op.create_index('ix_offers_listing_id', 'offers', ['listing_id'])


def downgrade() -> None:
    op.drop_index('ix_offers_listing_id', table_name='offers')
    op.drop_index('ix_offers_conversation_id', table_name='offers')
    op.drop_table('offers')
    sa.Enum(name='offer_status').drop(op.get_bind(), checkfirst=True)
