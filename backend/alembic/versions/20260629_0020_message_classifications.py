"""message types and reply classifications

Revision ID: 20260629_0020
Revises: 722f832c7f81
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260629_0020'
down_revision = '722f832c7f81'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('message_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('message_types.id')),
        sa.Column('description', sa.Text()), sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.UniqueConstraint('parent_id', 'name', name='uq_message_types_parent_name'))
    op.create_table('conversation_message_classifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('conversation_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('messages.id'), nullable=False),
        sa.Column('seller_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ebay_accounts.id')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('message_types.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('conversation_message_id', name='uq_message_classification_message'))
    for column in ('user_id','seller_account_id','message_type_id','conversation_id','created_at'):
        op.create_index(f'ix_message_classifications_{column}', 'conversation_message_classifications', [column])
    connection = op.get_bind()
    roots = ['Order Booking','Cancellation Sheet','Follow Up Messages','Invoice Messages','Awaiting Payment Follow Up','Tracking Follow Up','Bills']
    ids = {name: str(__import__('uuid').uuid4()) for name in roots}
    rows = [(ids[name], name, None, index) for index, name in enumerate(roots, 1)]
    rows += [(str(__import__('uuid').uuid4()), name, ids[parent], index) for parent, names in {
        'Follow Up Messages':['Cancellation Follow Up','Purchase Follow Up','VIP Inquiry Follow Up'],
        'Bills':['DHL','FEDEX']}.items() for index, name in enumerate(names, 1)]
    table = sa.table('message_types', sa.column('id', postgresql.UUID(as_uuid=True)), sa.column('name'), sa.column('parent_id', postgresql.UUID(as_uuid=True)), sa.column('display_order'))
    op.bulk_insert(table, [{'id': i, 'name': n, 'parent_id': p, 'display_order': o} for i,n,p,o in rows])


def downgrade() -> None:
    op.drop_table('conversation_message_classifications')
    op.drop_table('message_types')
