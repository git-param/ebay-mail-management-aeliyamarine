"""add task category quality weight

Revision ID: 20260803_0110
Revises: 20260803_0100
Create Date: 2026-08-03 01:10:00

"""
from alembic import op
import sqlalchemy as sa


revision = '20260803_0110'
down_revision = '20260803_0100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('task_categories', sa.Column('quality_weight', sa.Numeric(6, 2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('task_categories', 'quality_weight')
