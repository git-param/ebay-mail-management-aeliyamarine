"""create auth tables

Revision ID: 20260613_0001
Revises:
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa
from datetime import UTC, datetime
from passlib.context import CryptContext
from sqlalchemy.dialects import postgresql
from uuid import UUID


revision = '20260613_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    seeded_at = datetime(2026, 6, 13, tzinfo=UTC)
    password_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

    op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('must_reset_password', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=80), nullable=False),
        sa.Column('entity_type', sa.String(length=80), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'password_reset_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_password_reset_tokens_token_hash'), 'password_reset_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('jwt_id', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_refresh_tokens_jwt_id'), 'refresh_tokens', ['jwt_id'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)

    op.bulk_insert(
        sa.table(
            'roles',
            sa.column('id', postgresql.UUID(as_uuid=True)),
            sa.column('name', sa.String),
            sa.column('description', sa.String),
            sa.column('created_at', sa.DateTime(timezone=True)),
        ),
        [
            {
                'id': UUID('11111111-1111-1111-1111-111111111111'),
                'name': 'Admin',
                'description': 'Full platform access, including user management and audit logs.',
                'created_at': seeded_at,
            },
            {
                'id': UUID('22222222-2222-2222-2222-222222222222'),
                'name': 'Operations Manager',
                'description': 'Operational oversight, dashboard analytics, and account management.',
                'created_at': seeded_at,
            },
            {
                'id': UUID('33333333-3333-3333-3333-333333333333'),
                'name': 'Support Agent',
                'description': 'Conversation handling and personal dashboard access.',
                'created_at': seeded_at,
            },
        ],
    )

    op.bulk_insert(
        sa.table(
            'users',
            sa.column('id', postgresql.UUID(as_uuid=True)),
            sa.column('email', sa.String),
            sa.column('full_name', sa.String),
            sa.column('password_hash', sa.String),
            sa.column('role_id', postgresql.UUID(as_uuid=True)),
            sa.column('is_active', sa.Boolean),
            sa.column('must_reset_password', sa.Boolean),
            sa.column('created_at', sa.DateTime(timezone=True)),
            sa.column('updated_at', sa.DateTime(timezone=True)),
        ),
        [
            {
                'id': UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
                'email': 'admin@gmail.com',
                'full_name': 'Admin',
                'password_hash': password_context.hash('Admin@110'),
                'role_id': UUID('11111111-1111-1111-1111-111111111111'),
                'is_active': True,
                'must_reset_password': False,
                'created_at': seeded_at,
                'updated_at': seeded_at,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_jwt_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_token_hash'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_roles_name'), table_name='roles')
    op.drop_table('roles')
