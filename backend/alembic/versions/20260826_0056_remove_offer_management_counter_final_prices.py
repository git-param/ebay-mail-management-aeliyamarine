"""remove offer management counter and final prices

Revision ID: 20260826_0056
Revises: 20260826_0055
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa


revision = '20260826_0056'
down_revision = '20260826_0055'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column('offer_management_entries', 'counteroffer_price'):
        op.drop_column('offer_management_entries', 'counteroffer_price')
    if _has_column('offer_management_entries', 'final_price'):
        op.drop_column('offer_management_entries', 'final_price')
    op.execute(
        """
        UPDATE offer_management_entries
        SET is_high_value = CASE
            WHEN COALESCE(revised_price, listed_price) IS NULL THEN false
            WHEN COALESCE(revised_price, listed_price) > COALESCE(
                (
                    SELECT CASE WHEN value ~ '^[0-9]+(\\.[0-9]+)?$' THEN value::numeric END
                    FROM app_config_settings
                    WHERE config_key = 'offer.high_value_amount'
                    LIMIT 1
                ),
                500
            ) THEN true
            WHEN COALESCE(offer_quantity, 0) * COALESCE(revised_price, listed_price) > COALESCE(
                (
                    SELECT CASE WHEN value ~ '^[0-9]+(\\.[0-9]+)?$' THEN value::numeric END
                    FROM app_config_settings
                    WHERE config_key = 'offer.high_value_amount'
                    LIMIT 1
                ),
                500
            ) THEN true
            ELSE false
        END
        """
    )


def downgrade() -> None:
    if not _has_column('offer_management_entries', 'counteroffer_price'):
        op.add_column('offer_management_entries', sa.Column('counteroffer_price', sa.Numeric(12, 2), nullable=True))
    if not _has_column('offer_management_entries', 'final_price'):
        op.add_column('offer_management_entries', sa.Column('final_price', sa.Numeric(12, 2), nullable=True))
