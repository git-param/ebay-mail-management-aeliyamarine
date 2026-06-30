"""ensure message type keywords table exists

Revision ID: 20260630_0022
Revises: 20260630_0021

This corrective migration handles databases that were stamped with 0021 before
the message-type-keyword migration existed. It is intentionally idempotent so
fresh databases, where 0021 already created the table, remain unaffected.
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260630_0022'
down_revision = '20260630_0021'
branch_labels = None
depends_on = None


SEED_KEYWORDS = {
    'Order Booking': ['order booking', 'place order', 'purchase'],
    'Cancellation Sheet': ['cancel', 'cancellation', 'cancel order', 'refund', 'return'],
    'Follow Up Messages': ['follow up', 'update', 'status'],
    'Invoice Messages': ['invoice', 'payment proof', 'receipt'],
    'Awaiting Payment Follow Up': ['awaiting payment', 'payment pending', 'unpaid'],
    'Tracking Follow Up': ['tracking', 'shipment', 'delivered', 'fedex', 'dhl', 'awb', 'courier', 'package'],
    'Bills': ['bill', 'billing'],
}


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('message_type_keywords'):
        op.create_table(
            'message_type_keywords',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'message_type_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('message_types.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('keyword', sa.String(length=120), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('message_type_id', 'keyword', name='uq_message_type_keywords_type_keyword'),
        )
        op.create_index(
            'ix_message_type_keywords_message_type_id',
            'message_type_keywords',
            ['message_type_id'],
        )

    for type_name, keywords in SEED_KEYWORDS.items():
        message_type_id = connection.execute(
            sa.text('SELECT id FROM message_types WHERE name = :name LIMIT 1'),
            {'name': type_name},
        ).scalar()
        if not message_type_id:
            continue
        for keyword in keywords:
            connection.execute(
                sa.text(
                    'INSERT INTO message_type_keywords (id, message_type_id, keyword) '
                    'VALUES (:id, :message_type_id, :keyword) '
                    'ON CONFLICT ON CONSTRAINT uq_message_type_keywords_type_keyword DO NOTHING'
                ),
                {'id': uuid4(), 'message_type_id': message_type_id, 'keyword': keyword},
            )


def downgrade() -> None:
    # 0021 owns the table for normal migration histories. Dropping it here
    # would break downgrades on databases where 0021 created it.
    pass
