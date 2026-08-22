"""offer management followup close flow

Revision ID: 20260822_0049
Revises: 20260821_0048
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = '20260822_0049'
down_revision = '20260821_0048'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column['name'] == column_name
        for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    for value in ('OPEN', 'CLOSED'):
        op.execute(
            f"ALTER TYPE offer_management_status ADD VALUE IF NOT EXISTS '{value}'"
        )

    for value in (
        'DONE',
        'IGNORE',
        'SOLD',
        'NOT_ABLE_TO_MATCH_THE_PRICE',
    ):
        op.execute(
            f"ALTER TYPE offer_management_outcome ADD VALUE IF NOT EXISTS '{value}'"
        )

    if not _has_column(
        'offer_management_entries',
        'next_offer_followup',
    ):
        op.add_column(
            'offer_management_entries',
            sa.Column('next_offer_followup', sa.Date(), nullable=True),
        )


def downgrade() -> None:
    if _has_column(
        'offer_management_entries',
        'next_offer_followup',
    ):
        op.drop_column(
            'offer_management_entries',
            'next_offer_followup',
        )

