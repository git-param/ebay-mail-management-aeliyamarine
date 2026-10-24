"""Link reply templates to message types."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20261024_0064'
down_revision = '20261023_0063'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reply_templates', sa.Column('message_type_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_reply_templates_message_type_id_message_types',
        'reply_templates', 'message_types', ['message_type_id'], ['id'], ondelete='SET NULL',
    )
    op.execute("""
        DELETE FROM role_permissions
        USING roles, permissions
        WHERE role_permissions.role_id = roles.id
          AND role_permissions.permission_id = permissions.id
          AND upper(replace(roles.name, ' ', '_')) IN ('AGENT', 'SUPPORT_AGENT')
          AND permissions.code IN ('template.create', 'template.edit', 'template.delete')
    """)


def downgrade() -> None:
    op.drop_constraint('fk_reply_templates_message_type_id_message_types', 'reply_templates', type_='foreignkey')
    op.drop_column('reply_templates', 'message_type_id')
