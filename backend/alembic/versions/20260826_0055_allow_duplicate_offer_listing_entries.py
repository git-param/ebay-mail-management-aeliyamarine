"""allow duplicate offer listing entries

Revision ID: 20260826_0055
Revises: 20260826_0054
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa


revision = '20260826_0055'
down_revision = '20260826_0054'
branch_labels = None
depends_on = None


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints(table_name)
    return any(item.get('name') == constraint_name for item in constraints)


def upgrade() -> None:
    if _has_constraint('offer_management_entries', 'uq_offer_management_entries_listing_id'):
        op.drop_constraint('uq_offer_management_entries_listing_id', 'offer_management_entries', type_='unique')


def downgrade() -> None:
    if not _has_constraint('offer_management_entries', 'uq_offer_management_entries_listing_id'):
        op.create_unique_constraint('uq_offer_management_entries_listing_id', 'offer_management_entries', ['listing_id'])
