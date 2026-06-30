"""add configurable message type keywords

Revision ID: 20260630_0021
Revises: 20260629_0020
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260630_0021'
down_revision = '20260629_0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'message_type_keywords',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('message_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('message_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('keyword', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('message_type_id', 'keyword', name='uq_message_type_keywords_type_keyword'),
    )
    op.create_index('ix_message_type_keywords_message_type_id', 'message_type_keywords', ['message_type_id'])

    connection = op.get_bind()
    seed_keywords = {
        'Order Booking': ['order booking', 'place order', 'purchase'],
        'Cancellation Sheet': ['cancel', 'cancellation', 'cancel order', 'refund', 'return'],
        'Follow Up Messages': ['follow up', 'update', 'status'],
        'Invoice Messages': ['invoice', 'payment proof', 'receipt'],
        'Awaiting Payment Follow Up': ['awaiting payment', 'payment pending', 'unpaid'],
        'Tracking Follow Up': ['tracking', 'shipment', 'delivered', 'fedex', 'dhl', 'awb', 'courier', 'package'],
        'Bills': ['bill', 'billing'],
    }
    for type_name, keywords in seed_keywords.items():
        message_type_id = connection.execute(
            sa.text('SELECT id FROM message_types WHERE name = :name LIMIT 1'), {'name': type_name}
        ).scalar()
        if message_type_id:
            connection.execute(
                sa.text(
                    'INSERT INTO message_type_keywords (id, message_type_id, keyword) '
                    'VALUES (:id, :message_type_id, :keyword)'
                ),
                [
                    {'id': __import__('uuid').uuid4(), 'message_type_id': message_type_id, 'keyword': keyword}
                    for keyword in keywords
                ],
            )


def downgrade() -> None:
    op.drop_index('ix_message_type_keywords_message_type_id', table_name='message_type_keywords')
    op.drop_table('message_type_keywords')
