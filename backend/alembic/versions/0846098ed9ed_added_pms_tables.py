"""Added pms tables

Revision ID: 0846098ed9ed
Revises: 7d337f6d8bb6
Create Date: 2026-08-18 18:03:59.960815
"""

from alembic import op


revision = "0846098ed9ed"
down_revision = "7d337f6d8bb6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Finalize constraint naming after PMS daily-task objects
    were renamed by revision 7d337f6d8bb6.

    Enum conversion is intentionally NOT performed here because
    the PostgreSQL enum types were already renamed in the previous
    migration.
    """

    # ---------------------------------------------------------
    # Rename unique constraint to match the new table naming.
    #
    # The underlying table is already:
    # daily_task_entries
    #
    # Existing constraint may still have the old PMS-prefixed name.
    # ---------------------------------------------------------

    op.drop_constraint(
        "uq_pms_daily_task_entries_user_date",
        "daily_task_entries",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_daily_task_entries_user_date",
        "daily_task_entries",
        ["user_id", "entry_date"],
    )

    # IMPORTANT:
    # Do not alter day_type/error_level enums here.
    # Revision 7d337f6d8bb6 already renamed:
    #
    # pms_day_type -> daily_task_entry_day_type
    # pms_error_level -> daily_task_entry_error_level
    #
    # Do not touch ebay_api_usage here either because it is
    # unrelated to this PMS/daily-task migration.


def downgrade() -> None:
    """
    Restore the previous PMS-prefixed unique constraint name.

    Enum names are restored by downgrade of revision 7d337f6d8bb6,
    so they must not be changed here.
    """

    op.drop_constraint(
        "uq_daily_task_entries_user_date",
        "daily_task_entries",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_pms_daily_task_entries_user_date",
        "daily_task_entries",
        ["user_id", "entry_date"],
    )