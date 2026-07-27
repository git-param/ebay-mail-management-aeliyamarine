"""unique offer management listing id

Revision ID: 20260727_0034
Revises: 20260727_0033
Create Date: 2026-07-27
"""

from alembic import op


revision = '20260727_0034'
down_revision = '20260727_0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_offer_management_entries_listing_id',
        'offer_management_entries',
        ['listing_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_offer_management_entries_listing_id', 'offer_management_entries', type_='unique')
