"""Corrected name problem pms <-> daily task entry

Revision ID: 7d337f6d8bb6
Revises: 20260811_0045
Create Date: 2026-08-18 16:01:52.174825
"""

from alembic import op


revision = "7d337f6d8bb6"
down_revision = "20260811_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Rename PMS daily-task tables to their final names.

    IMPORTANT:
    We rename instead of create/drop so existing PMS scores,
    history records, IDs, timestamps and relationships are preserved.
    """

    # ---------------------------------------------------------
    # 1. Rename parent table first
    # ---------------------------------------------------------
    op.rename_table(
        "pms_daily_task_entries",
        "daily_task_entries",
    )

    # ---------------------------------------------------------
    # 2. Rename history/child table
    # ---------------------------------------------------------
    op.rename_table(
        "pms_daily_task_entry_history",
        "daily_task_entry_history",
    )

    # ---------------------------------------------------------
    # 3. Rename indexes
    # ---------------------------------------------------------
    op.execute("""
        ALTER INDEX IF EXISTS ix_pms_daily_task_entries_entry_date
        RENAME TO ix_daily_task_entries_entry_date
    """)

    op.execute("""
        ALTER INDEX IF EXISTS ix_pms_daily_task_entries_user_id
        RENAME TO ix_daily_task_entries_user_id
    """)

    op.execute("""
        ALTER INDEX IF EXISTS ix_pms_daily_task_entry_history_entry_id
        RENAME TO ix_daily_task_entry_history_entry_id
    """)

    # NOTE:
    # Do NOT drop ebay_api_usage indexes here.
    # That table is unrelated to this PMS naming migration.


def downgrade() -> None:
    """
    Restore the previous PMS table names.
    """

    # ---------------------------------------------------------
    # 1. Restore index names
    # ---------------------------------------------------------
    op.execute("""
        ALTER INDEX IF EXISTS ix_daily_task_entry_history_entry_id
        RENAME TO ix_pms_daily_task_entry_history_entry_id
    """)

    op.execute("""
        ALTER INDEX IF EXISTS ix_daily_task_entries_user_id
        RENAME TO ix_pms_daily_task_entries_user_id
    """)

    op.execute("""
        ALTER INDEX IF EXISTS ix_daily_task_entries_entry_date
        RENAME TO ix_pms_daily_task_entries_entry_date
    """)

    # ---------------------------------------------------------
    # 2. Rename child table back first
    # ---------------------------------------------------------
    op.rename_table(
        "daily_task_entry_history",
        "pms_daily_task_entry_history",
    )

    # ---------------------------------------------------------
    # 3. Rename parent table back
    # ---------------------------------------------------------
    op.rename_table(
        "daily_task_entries",
        "pms_daily_task_entries",
    )