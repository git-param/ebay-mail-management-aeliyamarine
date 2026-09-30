"""Track offers moved to saved history by staff."""
from alembic import op
import sqlalchemy as sa

revision = '20260930_0062'
down_revision = '20260926_0061'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('offers', sa.Column('done_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_offers_done_at', 'offers', ['done_at'])


def downgrade() -> None:
    op.drop_index('ix_offers_done_at', table_name='offers')
    op.drop_column('offers', 'done_at')
