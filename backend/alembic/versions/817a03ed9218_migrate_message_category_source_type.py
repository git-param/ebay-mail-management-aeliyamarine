from alembic import op


revision = "817a03ed9218"
down_revision = "ba1cf64ff078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL may require the new enum value to be committed before use.
    with op.get_context().autocommit_block():
        op.execute(
            """
            ALTER TYPE subtask_source_type
            ADD VALUE IF NOT EXISTS 'MESSAGE_TYPE'
            """
        )

    op.execute(
        """
        UPDATE subtasks
        SET source_type = 'MESSAGE_TYPE'
        WHERE source_type = 'MESSAGE_CATEGORY'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE subtasks
        SET source_type = 'MESSAGE_CATEGORY'
        WHERE source_type = 'MESSAGE_TYPE'
        """
    )