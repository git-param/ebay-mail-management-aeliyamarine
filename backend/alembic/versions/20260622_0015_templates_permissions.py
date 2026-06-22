"""Create template permissions and reply templates.

Revision ID: 20260622_0015
Revises: 20260620_0014
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260622_0015'
down_revision = '20260620_0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create permission-backed template management tables and default grants."""
    op.create_table(
        'permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_permissions_code'), 'permissions', ['code'], unique=True)
    op.create_table(
        'role_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permission_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id']),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_id', 'permission_id', name='uq_role_permissions_role_permission'),
    )
    op.create_table(
        'reply_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        """
        INSERT INTO permissions (id, code, description, created_at)
        VALUES
            ('10000000-0000-0000-0000-000000000101', 'template.view', 'View and use reply templates', now()),
            ('10000000-0000-0000-0000-000000000102', 'template.create', 'Create reply templates', now()),
            ('10000000-0000-0000-0000-000000000103', 'template.edit', 'Edit reply templates', now()),
            ('10000000-0000-0000-0000-000000000104', 'template.delete', 'Delete reply templates', now())
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT md5(roles.id::text || ':' || permissions.code)::uuid, roles.id, permissions.id, now()
        FROM roles
        JOIN permissions ON permissions.code IN ('template.view', 'template.create', 'template.edit', 'template.delete')
        WHERE roles.name IN ('Admin', 'Operations Manager')
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT md5(roles.id::text || ':' || permissions.code)::uuid, roles.id, permissions.id, now()
        FROM roles
        JOIN permissions ON permissions.code = 'template.view'
        WHERE roles.name = 'Support Agent'
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop template management tables."""
    op.drop_table('reply_templates')
    op.drop_table('role_permissions')
    op.drop_index(op.f('ix_permissions_code'), table_name='permissions')
    op.drop_table('permissions')
