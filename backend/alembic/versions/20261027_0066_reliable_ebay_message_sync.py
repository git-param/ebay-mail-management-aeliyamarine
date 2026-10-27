"""Make eBay message sync account-scoped and observable."""

from alembic import op
import sqlalchemy as sa


revision = '20261027_0066'
down_revision = '20261024_0065'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('uq_conversations_provider_external_id', 'conversations', type_='unique')
    op.create_unique_constraint(
        'uq_conversations_provider_account_external_id',
        'conversations',
        ['provider', 'provider_account_id', 'provider_conversation_id'],
    )
    op.add_column('ebay_accounts', sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ebay_accounts', sa.Column('last_sync_error', sa.Text(), nullable=True))
    op.add_column('ebay_accounts', sa.Column('last_sync_recovery_at', sa.DateTime(timezone=True), nullable=True))
    op.execute('UPDATE ebay_accounts SET last_successful_sync_at = last_sync_at WHERE last_sync_at IS NOT NULL')
    op.execute(
        """
        INSERT INTO app_config_settings (
            id, section, config_key, label, value, value_type, description,
            is_editable, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), 'api', 'api.ebay_message_sync_overlap_minutes',
            'eBay message sync overlap', '5', 'integer',
            'Minutes re-read before each account checkpoint to recover messages around sync boundaries.',
            true, now(), now()
        )
        ON CONFLICT (config_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM app_config_settings WHERE config_key = 'api.ebay_message_sync_overlap_minutes'")
    op.drop_column('ebay_accounts', 'last_sync_recovery_at')
    op.drop_column('ebay_accounts', 'last_sync_error')
    op.drop_column('ebay_accounts', 'last_successful_sync_at')
    op.drop_constraint('uq_conversations_provider_account_external_id', 'conversations', type_='unique')
    op.create_unique_constraint(
        'uq_conversations_provider_external_id',
        'conversations',
        ['provider', 'provider_conversation_id'],
    )
