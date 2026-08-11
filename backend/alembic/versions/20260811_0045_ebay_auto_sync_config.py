"""ebay auto sync config

Revision ID: 20260811_0045
Revises: 20260811_0044
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op


revision = '20260811_0045'
down_revision = '20260811_0044'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO app_config_settings (
            id, section, config_key, label, value, value_type, description, is_editable, created_at, updated_at
        )
        VALUES
            (
                gen_random_uuid(),
                'api',
                'api.ebay_auto_sync_interval_hours',
                'eBay auto sync interval',
                '6',
                'integer',
                'Hours to wait after the latest eBay sync before auto sync runs again.',
                true,
                now(),
                now()
            ),
            (
                gen_random_uuid(),
                'api',
                'api.ebay_auto_sync_enabled',
                'eBay auto sync enabled',
                'false',
                'boolean',
                'Controlled from the eBay Accounts page.',
                false,
                now(),
                now()
            )
        ON CONFLICT (config_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM app_config_settings
        WHERE config_key IN (
            'api.ebay_auto_sync_interval_hours',
            'api.ebay_auto_sync_enabled'
        )
        """
    )
