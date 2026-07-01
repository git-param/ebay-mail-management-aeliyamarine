"""fix conversation category manual-selection default

Revision ID: 20260630_0023
Revises: 20260630_0022

The column exists in some deployed databases without a server default, but is
absent from databases built solely from this repository's migration history.
This corrective migration safely handles both states.
"""

from alembic import op
import sqlalchemy as sa


revision = '20260630_0023'
down_revision = '20260630_0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column['name'] for column in sa.inspect(connection).get_columns('conversations')}

    if 'category_manually_selected' not in columns:
        op.add_column(
            'conversations',
            sa.Column(
                'category_manually_selected',
                sa.Boolean(),
                nullable=True,
                server_default=sa.false(),
            ),
        )

    # Backfill first: setting NOT NULL before this UPDATE would fail on legacy rows.
    connection.execute(
        sa.text(
            'UPDATE conversations '
            'SET category_manually_selected = FALSE '
            'WHERE category_manually_selected IS NULL'
        )
    )
    op.alter_column(
        'conversations',
        'category_manually_selected',
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'category_manually_selected')
