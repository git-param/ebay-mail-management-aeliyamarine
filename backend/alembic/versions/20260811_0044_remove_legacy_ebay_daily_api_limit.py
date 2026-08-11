"""remove legacy ebay daily api limit

Revision ID: 20260811_0044
Revises: 20260811_0043
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op


revision = '20260811_0044'
down_revision = '20260811_0043'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM app_config_settings WHERE config_key = 'api.ebay_daily_api_limit'")


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO app_config_settings (
            id, section, config_key, label, value, value_type, description, is_editable, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(),
            'api',
            'api.ebay_daily_api_limit',
            'eBay daily API limit',
            '100',
            'integer',
            'Maximum eBay API calls allowed per day.',
            true,
            now(),
            now()
        )
        ON CONFLICT (config_key) DO NOTHING
        """
    )
