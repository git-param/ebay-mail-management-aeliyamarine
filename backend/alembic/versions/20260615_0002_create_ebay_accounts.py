"""create ebay accounts

Revision ID: 20260615_0002
Revises: 20260613_0001
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260615_0002'
down_revision = '20260613_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    environment_enum = postgresql.ENUM('SANDBOX', 'PRODUCTION', name='ebay_environment', create_type=False)
    connection_status_enum = postgresql.ENUM(
        'CONNECTED',
        'DISCONNECTED',
        'EXPIRED',
        name='ebay_connection_status',
        create_type=False,
    )
    environment_enum.create(op.get_bind(), checkfirst=True)
    connection_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'ebay_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_name', sa.String(length=255), nullable=False),
        sa.Column('ebay_username', sa.String(length=255), nullable=False),
        sa.Column('environment', environment_enum, nullable=False),
        sa.Column('connection_status', connection_status_enum, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('oauth_state', sa.String(length=255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ebay_user_id', sa.String(length=255), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_status', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ebay_accounts_ebay_username'), 'ebay_accounts', ['ebay_username'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ebay_accounts_ebay_username'), table_name='ebay_accounts')
    op.drop_table('ebay_accounts')
    postgresql.ENUM(name='ebay_connection_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='ebay_environment').drop(op.get_bind(), checkfirst=True)
