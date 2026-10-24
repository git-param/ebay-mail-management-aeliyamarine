"""Add shared main tasks without rewriting historical task entries."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261024_0065'
down_revision = '20261024_0064'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'main_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(160), nullable=False, unique=True),
        sa.Column('source_type', sa.String(40), nullable=False),
        sa.Column('message_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('message_types.id', ondelete='SET NULL'), nullable=True),
        sa.Column('weight', sa.Numeric(6, 2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("""
        INSERT INTO main_tasks (id, name, source_type, weight, is_active, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000001', 'Other', 'OTHER', 10, true, now(), now())
    """)


def downgrade() -> None:
    op.drop_table('main_tasks')
