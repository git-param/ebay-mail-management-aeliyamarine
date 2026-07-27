"""create app config settings

Revision ID: 20260727_0033
Revises: 20260727_0032
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260727_0033'
down_revision = '20260727_0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'app_config_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('section', sa.String(length=80), nullable=False),
        sa.Column('config_key', sa.String(length=120), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('value_type', sa.String(length=40), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_editable', sa.Boolean(), nullable=False),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_key', name='uq_app_config_settings_key'),
    )
    op.create_index(op.f('ix_app_config_settings_section'), 'app_config_settings', ['section'])
    op.create_index(op.f('ix_app_config_settings_config_key'), 'app_config_settings', ['config_key'])
    op.execute(
        """
        INSERT INTO app_config_settings (id, section, config_key, label, value, value_type, description, is_editable)
        VALUES
        (gen_random_uuid(), 'offer', 'offer.high_value_amount', 'High value amount', '500', 'decimal', 'Offer entries are high value when unit offer or quantity multiplied by offer amount reaches this value.', true),
        (gen_random_uuid(), 'api', 'api.ebay_daily_api_limit', 'eBay daily API limit', '100', 'integer', 'Maximum eBay API calls allowed per day.', true)
        ON CONFLICT (config_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_app_config_settings_config_key'), table_name='app_config_settings')
    op.drop_index(op.f('ix_app_config_settings_section'), table_name='app_config_settings')
    op.drop_table('app_config_settings')
