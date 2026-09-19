"""Add reply template categories.

Revision ID: 20260919_0057
Revises: 20260826_0056
Create Date: 2026-09-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260919_0057'
down_revision = '20260826_0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create template categories and allow templates to reference them."""
    op.create_table(
        'reply_template_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_reply_template_categories_name'),
    )
    op.add_column('reply_templates', sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_reply_templates_category_id_reply_template_categories',
        'reply_templates',
        'reply_template_categories',
        ['category_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Remove template categories."""
    op.drop_constraint(
        'fk_reply_templates_category_id_reply_template_categories',
        'reply_templates',
        type_='foreignkey',
    )
    op.drop_column('reply_templates', 'category_id')
    op.drop_table('reply_template_categories')
