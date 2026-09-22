"""offer management offered price

Revision ID: 20260826_0054
Revises: 20260825_0053
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa


revision = '20260826_0054'
down_revision = '20260825_0053'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('offer_management_entries', sa.Column('offered_price', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('offer_management_entries', 'offered_price')
