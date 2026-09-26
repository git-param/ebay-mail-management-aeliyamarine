"""Extend existing offers with authoritative Trading state and durable operations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '20260926_0061'
down_revision = '20260926_0060'
branch_labels = None
depends_on = None


def upgrade():
    additions = [
        sa.Column('record_source', sa.String(32), nullable=False, server_default='LEGACY_UNKNOWN'),
        sa.Column('provider_status', sa.String(80)), sa.Column('provider_role', sa.String(32)),
        sa.Column('provider_snapshot', pg.JSONB()), sa.Column('listing_snapshot', pg.JSONB()),
        sa.Column('received_at', sa.DateTime(timezone=True)), sa.Column('received_at_source', sa.String(40)),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_seen_at', sa.DateTime(timezone=True)), sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('last_seen_sync_id', pg.UUID(as_uuid=True)),
        sa.Column('reconciliation_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    ]
    for column in additions:
        op.add_column('offers', column)
    op.create_foreign_key('offers_last_seen_sync_id_fkey', 'offers', 'sync_logs', ['last_seen_sync_id'], ['id'], ondelete='SET NULL')
    op.execute("UPDATE offers SET first_seen_at=created_at")
    op.execute("UPDATE offers SET record_source='MESSAGE_PARSE' WHERE raw_payload->>'source'='on_demand_message_parse'")
    op.execute("UPDATE offers SET record_source='DERIVED' WHERE raw_payload ? 'derivedEvent' OR provider_offer_id LIKE '%' || chr(58) || 'seller-counteroffer-submitted'")
    # Historical role is unknown: these rows stay excluded until verified refresh.
    op.execute("UPDATE offers SET provider_status=raw_payload->>'status' WHERE record_source='LEGACY_UNKNOWN' AND raw_payload->>'offerId'=provider_offer_id")
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes('offers'):
        if index['name'] == 'ix_offers_provider_offer_id' and index['unique']:
            op.drop_index(index['name'], table_name='offers')
            op.create_index(index['name'], 'offers', ['provider_offer_id'])
    for fk in inspector.get_foreign_keys('offers'):
        if fk['constrained_columns'] in [['conversation_id'], ['message_id']]:
            op.drop_constraint(fk['name'], 'offers', type_='foreignkey')
            op.create_foreign_key(fk['name'], 'offers', fk['referred_table'], fk['constrained_columns'], fk['referred_columns'], ondelete='SET NULL')
    op.create_index('ix_offers_current_account_status_expiry', 'offers', ['account_id', 'provider_status', 'expires_at'])
    op.create_index('ix_offers_reconciliation', 'offers', ['account_id', 'reconciliation_required', 'last_synced_at'])
    for column in [sa.Column('last_reconciled_at', sa.DateTime(timezone=True)), sa.Column('next_reconcile_at', sa.DateTime(timezone=True)), sa.Column('reconcile_attempts', sa.Integer(), nullable=False, server_default='0'), sa.Column('reconcile_page', sa.Integer(), nullable=False, server_default='1')]:
        op.add_column('ebay_best_offer_listing_sync_states', column)
    # Freeze supporting schemas here so later model changes cannot change this migration.
    op.create_table('ebay_best_offer_actions',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('offer_id', pg.UUID(as_uuid=True), sa.ForeignKey('offers.id'), nullable=False),
        sa.Column('account_id', pg.UUID(as_uuid=True), sa.ForeignKey('ebay_accounts.id'), nullable=False),
        sa.Column('actor_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('idempotency_key', pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('expected_version', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('parameters', pg.JSONB(), nullable=False),
        sa.Column('state', sa.String(40), nullable=False),
        sa.Column('provider_result', pg.JSONB()), sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(timezone=True)), sa.Column('completed_at', sa.DateTime(timezone=True)))
    op.create_index('ix_ebay_best_offer_actions_offer_id', 'ebay_best_offer_actions', ['offer_id'])
    op.create_index('ix_ebay_best_offer_actions_state', 'ebay_best_offer_actions', ['state'])
    op.create_index('uq_best_offer_unresolved_action', 'ebay_best_offer_actions', ['offer_id'], unique=True,
                    postgresql_where=sa.text("state IN ('PREPARED','DISPATCHING','RECONCILIATION_REQUIRED')"))
    op.create_table('ebay_api_call_attempts',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('usage_id', pg.UUID(as_uuid=True), sa.ForeignKey('ebay_api_usage.id'), nullable=False),
        sa.Column('account_id', pg.UUID(as_uuid=True), sa.ForeignKey('ebay_accounts.id', ondelete='SET NULL')),
        sa.Column('operation', sa.String(80), nullable=False),
        sa.Column('job_id', pg.UUID(as_uuid=True), sa.ForeignKey('sync_logs.id', ondelete='SET NULL')),
        sa.Column('action_id', pg.UUID(as_uuid=True), sa.ForeignKey('ebay_best_offer_actions.id', ondelete='SET NULL')),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.String(40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    for column in ['usage_id', 'account_id', 'operation', 'created_at']:
        op.create_index('ix_ebay_api_call_attempts_' + column, 'ebay_api_call_attempts', [column])
    op.create_index('uq_best_offer_account_job', 'sync_logs', ['provider_account_id'], unique=True,
                    postgresql_where=sa.text("sync_type='EBAY_BEST_OFFER_SYNC' AND status IN ('PENDING','RUNNING')"))
    op.create_index('uq_best_offer_batch_job', 'sync_logs', ['sync_type'], unique=True,
                    postgresql_where=sa.text("sync_type='EBAY_BEST_OFFER_BATCH' AND status IN ('PENDING','RUNNING')"))
    op.execute("UPDATE app_config_settings SET value='2500000', label='eBay Trading Best Offer daily limit', updated_at=now() WHERE config_key='api.ebay_bestseller_daily_limit'")
    for key, value, kind in [('enabled', 'false', 'boolean'), ('interval_minutes', '5', 'integer'), ('account_ids', '[]', 'text')]:
        op.get_bind().execute(sa.text("INSERT INTO app_config_settings (id,section,config_key,label,value,value_type,is_editable,created_at,updated_at) VALUES (gen_random_uuid(),'offer',:key,:label,:value,:kind,false,now(),now()) ON CONFLICT (config_key) DO NOTHING"), {'key': 'offer.best_offer_' + key, 'label': 'Best Offer ' + key, 'value': value, 'kind': kind})
    op.execute("INSERT INTO permissions (id,code,description,created_at) VALUES (gen_random_uuid(),'offer.respond','Respond to authoritative seller Best Offers',now()) ON CONFLICT (code) DO NOTHING")
    op.execute("INSERT INTO role_permissions (id,role_id,permission_id,created_at) SELECT gen_random_uuid(),r.id,p.id,now() FROM roles r CROSS JOIN permissions p WHERE p.code='offer.respond' AND upper(replace(r.name,' ','_')) IN ('ADMIN','OPS_MANAGER','OPERATIONS_MANAGER','AGENT','SUPPORT_AGENT') ON CONFLICT (role_id,permission_id) DO NOTHING")


def downgrade():
    # Refuse a destructive downgrade after operational history has accumulated.
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM ebay_best_offer_actions) OR EXISTS(SELECT 1 FROM ebay_api_call_attempts)')):
        raise RuntimeError('Archive Best Offer action/attempt history before downgrade')
    op.drop_table('ebay_api_call_attempts')
    op.drop_table('ebay_best_offer_actions')
    for name in ['uq_best_offer_account_job', 'uq_best_offer_batch_job']:
        op.drop_index(name, table_name='sync_logs')
    for name in ['ix_offers_current_account_status_expiry', 'ix_offers_reconciliation']:
        op.drop_index(name, table_name='offers')
    op.drop_constraint('offers_last_seen_sync_id_fkey', 'offers', type_='foreignkey')
    for name in ['record_source','provider_status','provider_role','provider_snapshot','listing_snapshot','received_at','received_at_source','first_seen_at','last_seen_at','last_synced_at','last_seen_sync_id','reconciliation_required','version']:
        op.drop_column('offers', name)
    for name in ['last_reconciled_at','next_reconcile_at','reconcile_attempts','reconcile_page']:
        op.drop_column('ebay_best_offer_listing_sync_states', name)
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code='offer.respond')")
    op.execute("DELETE FROM permissions WHERE code='offer.respond'")
    op.execute("DELETE FROM app_config_settings WHERE config_key LIKE 'offer.best_offer_%'")
    # The 2.5M entitlement and SET NULL history protection remain valid independently.
