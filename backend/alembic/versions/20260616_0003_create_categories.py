"""create categories

Revision ID: 20260616_0003
Revises: 20260615_0002
Create Date: 2026-06-16

"""
from datetime import UTC, datetime
from uuid import UUID

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260616_0003'
down_revision = '20260615_0002'
branch_labels = None
depends_on = None


ADMIN_USER_ID = UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')

DEFAULT_CATEGORIES = [
    {
        'id': UUID('10000000-0000-0000-0000-000000000001'),
        'name': 'Shipping',
        'description': 'Delivery, tracking, courier, and shipment questions.',
        'color': '#2563eb',
        'sla_hours': 24,
        'keywords': ['tracking', 'delivery', 'courier', 'shipment'],
    },
    {
        'id': UUID('10000000-0000-0000-0000-000000000002'),
        'name': 'Refund',
        'description': 'Refund, reimbursement, and money-back requests.',
        'color': '#16a34a',
        'sla_hours': 24,
        'keywords': ['refund', 'reimbursement', 'money back'],
    },
    {
        'id': UUID('10000000-0000-0000-0000-000000000003'),
        'name': 'Return',
        'description': 'Return requests, labels, and send-back instructions.',
        'color': '#f97316',
        'sla_hours': 48,
        'keywords': ['return', 'return label', 'send back'],
    },
    {
        'id': UUID('10000000-0000-0000-0000-000000000004'),
        'name': 'Product Inquiry',
        'description': 'Product details, availability, fit, and compatibility questions.',
        'color': '#7c3aed',
        'sla_hours': 24,
        'keywords': ['product', 'available', 'compatibility', 'size', 'details'],
    },
    {
        'id': UUID('10000000-0000-0000-0000-000000000005'),
        'name': 'Technical Issue',
        'description': 'Technical problems, defects, or setup issues.',
        'color': '#dc2626',
        'sla_hours': 12,
        'keywords': ['technical', 'issue', 'defect', 'broken', 'not working'],
    },
    {
        'id': UUID('10000000-0000-0000-0000-000000000006'),
        'name': 'Order Cancellation',
        'description': 'Order cancellation requests before fulfillment.',
        'color': '#64748b',
        'sla_hours': 8,
        'keywords': ['cancel', 'cancellation', 'cancel order'],
    },
    {
        'id': UUID('10000000-0000-0000-0000-000000000007'),
        'name': 'Other',
        'description': 'Fallback category when no keyword rule matches.',
        'color': '#0f172a',
        'sla_hours': 48,
        'keywords': [],
    },
]


def upgrade() -> None:
    seeded_at = datetime(2026, 6, 16, tzinfo=UTC)

    op.create_table(
        'categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=False),
        sa.Column('sla_hours', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_categories_name_lower', 'categories', [sa.text('lower(name)')], unique=True)
    op.create_index(op.f('ix_categories_is_active'), 'categories', ['is_active'], unique=False)

    op.create_table(
        'category_keywords',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('keyword', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_category_keywords_category_id'), 'category_keywords', ['category_id'], unique=False)
    op.create_index(
        'ix_category_keywords_category_id_keyword_lower',
        'category_keywords',
        ['category_id', sa.text('lower(keyword)')],
        unique=True,
    )

    category_table = sa.table(
        'categories',
        sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('description', sa.Text),
        sa.column('color', sa.String),
        sa.column('sla_hours', sa.Integer),
        sa.column('is_active', sa.Boolean),
        sa.column('created_by', postgresql.UUID(as_uuid=True)),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    keyword_table = sa.table(
        'category_keywords',
        sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('category_id', postgresql.UUID(as_uuid=True)),
        sa.column('keyword', sa.String),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )

    op.bulk_insert(
        category_table,
        [
            {
                'id': category['id'],
                'name': category['name'],
                'description': category['description'],
                'color': category['color'],
                'sla_hours': category['sla_hours'],
                'is_active': True,
                'created_by': ADMIN_USER_ID,
                'created_at': seeded_at,
                'updated_at': seeded_at,
            }
            for category in DEFAULT_CATEGORIES
        ],
    )

    keyword_rows = []
    keyword_index = 1
    for category in DEFAULT_CATEGORIES:
        for keyword in category['keywords']:
            keyword_rows.append(
                {
                    'id': UUID(f'20000000-0000-0000-0000-{keyword_index:012d}'),
                    'category_id': category['id'],
                    'keyword': keyword,
                    'created_at': seeded_at,
                }
            )
            keyword_index += 1

    if keyword_rows:
        op.bulk_insert(keyword_table, keyword_rows)


def downgrade() -> None:
    op.drop_index('ix_category_keywords_category_id_keyword_lower', table_name='category_keywords')
    op.drop_index(op.f('ix_category_keywords_category_id'), table_name='category_keywords')
    op.drop_table('category_keywords')
    op.drop_index(op.f('ix_categories_is_active'), table_name='categories')
    op.drop_index('ix_categories_name_lower', table_name='categories')
    op.drop_table('categories')
