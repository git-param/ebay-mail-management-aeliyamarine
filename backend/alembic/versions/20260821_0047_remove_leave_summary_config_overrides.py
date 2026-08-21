"""remove leave summary config overrides

Revision ID: 20260821_0047
Revises: 3d1ee3134faa
Create Date: 2026-08-21 00:00:00.000000
"""

from alembic import op


revision = '20260821_0047'
down_revision = '3d1ee3134faa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM app_config_settings WHERE config_key LIKE 'leave.summary.override.%'")


def downgrade() -> None:
    pass
