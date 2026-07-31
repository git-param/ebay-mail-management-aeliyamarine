"""pms daily task entries

Revision ID: 20260730_0041
Revises: 20260728_0040
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260730_0041"
down_revision = "20260728_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # create_type=False prevents op.create_table() from trying
    # to create these PostgreSQL enum types a second time.
    day_type = postgresql.ENUM(
        "WORKING_DAY",
        "HOLIDAY",
        "SUNDAY",
        "LEAVE",
        name="pms_day_type",
        create_type=False,
    )

    feedback_status = postgresql.ENUM(
        "GIVEN",
        "PENDING",
        name="pms_feedback_status",
        create_type=False,
    )

    # Create only when they do not already exist.
    day_type.create(bind, checkfirst=True)
    feedback_status.create(bind, checkfirst=True)

    op.add_column(
        "sold_posting_line_items",
        sa.Column(
            "copied_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_sold_posting_line_items_copied_by_user_id_users",
        "sold_posting_line_items",
        "users",
        ["copied_by_user_id"],
        ["id"],
    )

    op.create_table(
        "pms_daily_task_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "entry_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "day_type",
            day_type,
            nullable=False,
        ),
        sa.Column(
            "sold_posting_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "m2m_vip_followups_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tracking_sheet_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "purchase_sheet_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "booking_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "other_general_work_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "final_score_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "sla_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("20"),
        ),
        sa.Column(
            "feedback_status",
            feedback_status,
            nullable=False,
        ),
        sa.Column(
            "particulars_error_note",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "sla_remarks",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "entry_date",
            name="uq_pms_daily_task_entries_user_date",
        ),
    )

    op.create_index(
        "ix_pms_daily_task_entries_entry_date",
        "pms_daily_task_entries",
        ["entry_date"],
    )

    op.create_index(
        "ix_pms_daily_task_entries_user_id",
        "pms_daily_task_entries",
        ["user_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        "ix_pms_daily_task_entries_user_id",
        table_name="pms_daily_task_entries",
    )

    op.drop_index(
        "ix_pms_daily_task_entries_entry_date",
        table_name="pms_daily_task_entries",
    )

    op.drop_table("pms_daily_task_entries")

    op.drop_constraint(
        "fk_sold_posting_line_items_copied_by_user_id_users",
        "sold_posting_line_items",
        type_="foreignkey",
    )

    op.drop_column(
        "sold_posting_line_items",
        "copied_by_user_id",
    )

    postgresql.ENUM(
        name="pms_feedback_status",
        create_type=False,
    ).drop(bind, checkfirst=True)

    postgresql.ENUM(
        name="pms_day_type",
        create_type=False,
    ).drop(bind, checkfirst=True)