"""clean ebay offer model and stop stale offer parsing

Revision ID: f3d5c50fa008
Revises: 8602578c13dd
Create Date: 2026-07-08 10:45:46.475271

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = 'f3d5c50fa008'
down_revision = '8602578c13dd'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [column["name"] for column in inspector.get_columns(table_name)]
    return column_name in columns


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [index["name"] for index in inspector.get_indexes(table_name)]
    return index_name in indexes


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)

    unique_constraints = [
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
    ]

    foreign_keys = [
        constraint["name"]
        for constraint in inspector.get_foreign_keys(table_name)
    ]

    return constraint_name in unique_constraints or constraint_name in foreign_keys


def upgrade() -> None:
    # 1. Add new production columns.
    if not _has_column("offers", "provider"):
        op.add_column(
            "offers",
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="EBAY"),
        )

    if not _has_column("offers", "message_id"):
        op.add_column(
            "offers",
            sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _has_column("offers", "raw_text"):
        op.add_column(
            "offers",
            sa.Column("raw_text", sa.Text(), nullable=True),
        )

    if not _has_column("offers", "created_at_provider"):
        op.add_column(
            "offers",
            sa.Column("created_at_provider", sa.DateTime(timezone=True), nullable=True),
        )

    # 2. Backfill provider and updated_at safely.
    op.execute("UPDATE offers SET provider = 'EBAY' WHERE provider IS NULL")
    op.execute("UPDATE offers SET updated_at = NOW() WHERE updated_at IS NULL")

    # 3. Make updated_at non-null with DB default.
    if _has_column("offers", "updated_at"):
        op.alter_column(
            "offers",
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        )

    # 4. Add indexes.
    if not _has_index("offers", "ix_offers_account_id"):
        op.create_index("ix_offers_account_id", "offers", ["account_id"])

    if not _has_index("offers", "ix_offers_conversation_id"):
        op.create_index("ix_offers_conversation_id", "offers", ["conversation_id"])

    if not _has_index("offers", "ix_offers_message_id"):
        op.create_index("ix_offers_message_id", "offers", ["message_id"])

    if not _has_index("offers", "ix_offers_lookup"):
        op.create_index(
            "ix_offers_lookup",
            "offers",
            ["account_id", "listing_id", "buyer_username"],
        )

    # 5. Add FK from offers.message_id -> messages.id.
    if not _has_constraint("offers", "fk_offers_message_id_messages"):
        op.create_foreign_key(
            "fk_offers_message_id_messages",
            "offers",
            "messages",
            ["message_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 6. Replace old global uniqueness with account-aware uniqueness.
    if _has_constraint("offers", "offers_provider_offer_id_key"):
        op.drop_constraint("offers_provider_offer_id_key", "offers", type_="unique")

    if not _has_constraint("offers", "uq_offers_provider_account_offer_id"):
        op.create_unique_constraint(
            "uq_offers_provider_account_offer_id",
            "offers",
            ["provider", "account_id", "provider_offer_id"],
        )

    # 7. Drop old ambiguous message column.
    # We now use raw_text + raw_payload instead.
    if _has_column("offers", "message"):
        op.drop_column("offers", "message")


def downgrade() -> None:
    # Re-add old message column.
    if not _has_column("offers", "message"):
        op.add_column(
            "offers",
            sa.Column("message", sa.String(length=2000), nullable=True),
        )

    # Remove new uniqueness.
    if _has_constraint("offers", "uq_offers_provider_account_offer_id"):
        op.drop_constraint("uq_offers_provider_account_offer_id", "offers", type_="unique")

    # Restore old uniqueness.
    if not _has_constraint("offers", "offers_provider_offer_id_key"):
        op.create_unique_constraint(
            "offers_provider_offer_id_key",
            "offers",
            ["provider_offer_id"],
        )

    # Drop FK.
    if _has_constraint("offers", "fk_offers_message_id_messages"):
        op.drop_constraint("fk_offers_message_id_messages", "offers", type_="foreignkey")

    # Drop indexes.
    if _has_index("offers", "ix_offers_lookup"):
        op.drop_index("ix_offers_lookup", table_name="offers")

    if _has_index("offers", "ix_offers_message_id"):
        op.drop_index("ix_offers_message_id", table_name="offers")

    if _has_index("offers", "ix_offers_conversation_id"):
        op.drop_index("ix_offers_conversation_id", table_name="offers")

    if _has_index("offers", "ix_offers_account_id"):
        op.drop_index("ix_offers_account_id", table_name="offers")

    # Drop added columns.
    if _has_column("offers", "created_at_provider"):
        op.drop_column("offers", "created_at_provider")

    if _has_column("offers", "raw_text"):
        op.drop_column("offers", "raw_text")

    if _has_column("offers", "message_id"):
        op.drop_column("offers", "message_id")

    if _has_column("offers", "provider"):
        op.drop_column("offers", "provider")

    # Restore updated_at nullable behavior.
    if _has_column("offers", "updated_at"):
        op.alter_column(
            "offers",
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        )