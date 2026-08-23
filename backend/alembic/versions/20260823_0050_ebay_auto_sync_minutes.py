"""ebay auto sync minutes

Revision ID: 20260823_0050
Revises: 20260822_0049
Create Date: 2026-08-23 00:00:00.000000
"""

from alembic import op


revision = '20260823_0050'
down_revision = '20260822_0049'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO app_config_settings (
            id, section, config_key, label, value, value_type, description, is_editable, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            'api',
            'api.ebay_auto_sync_interval_minutes',
            'eBay auto sync interval',
            GREATEST(COALESCE(NULLIF(hours.value, '')::integer, 6) * 60, 2)::text,
            'integer',
            'Minutes to wait after the latest eBay sync before auto sync runs again. Minimum 2 minutes.',
            true,
            now(),
            now()
        FROM (SELECT 1) seed
        LEFT JOIN app_config_settings hours
            ON hours.config_key = 'api.ebay_auto_sync_interval_hours'
        ON CONFLICT (config_key) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE app_config_settings
        SET
            description = 'Legacy hour interval used when minute interval is not configured.',
            is_editable = false,
            updated_at = now()
        WHERE config_key = 'api.ebay_auto_sync_interval_hours'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM app_config_settings
        WHERE config_key = 'api.ebay_auto_sync_interval_minutes'
        """
    )
    op.execute(
        """
        UPDATE app_config_settings
        SET
            description = 'Hours to wait after the latest eBay sync before auto sync runs again.',
            is_editable = true,
            updated_at = now()
        WHERE config_key = 'api.ebay_auto_sync_interval_hours'
        """
    )
