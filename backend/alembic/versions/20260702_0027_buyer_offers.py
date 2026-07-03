"""support incoming buyer offers

Revision ID: 20260702_0027
Revises: 20260702_0026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260702_0027'
down_revision = '20260702_0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    direction = postgresql.ENUM('INCOMING', 'OUTGOING', name='offer_direction', create_type=False)
    direction.create(op.get_bind(), checkfirst=True)
    op.add_column('offers', sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('offers', sa.Column('direction', direction, nullable=False, server_default='OUTGOING'))
    op.add_column('offers', sa.Column('offer_type', sa.String(50), nullable=True))
    op.add_column('offers', sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'))
    op.alter_column('offers', 'conversation_id', nullable=True)
    op.drop_constraint('offers_conversation_id_fkey', 'offers', type_='foreignkey')
    op.create_foreign_key('offers_conversation_id_fkey', 'offers', 'conversations', ['conversation_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('offers_account_id_fkey', 'offers', 'ebay_accounts', ['account_id'], ['id'])
    op.create_index('ix_offers_account_id', 'offers', ['account_id'])


def downgrade() -> None:
    op.drop_index('ix_offers_account_id', table_name='offers')
    op.drop_constraint('offers_account_id_fkey', 'offers', type_='foreignkey')
    op.drop_constraint('offers_conversation_id_fkey', 'offers', type_='foreignkey')
    op.create_foreign_key('offers_conversation_id_fkey', 'offers', 'conversations', ['conversation_id'], ['id'], ondelete='CASCADE')
    op.alter_column('offers', 'conversation_id', nullable=False)
    op.drop_column('offers', 'quantity')
    op.drop_column('offers', 'offer_type')
    op.drop_column('offers', 'direction')
    op.drop_column('offers', 'account_id')
    postgresql.ENUM(name='offer_direction').drop(op.get_bind(), checkfirst=True)
