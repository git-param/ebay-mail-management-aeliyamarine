"""
repair_sla_history.py
---------------------

One-time reconciliation utility for conversation SLA history.

WHY THIS SCRIPT EXISTS
======================

Older eBay message synchronization started SLA cycles when buyer messages were
discovered, but historically did not always complete those cycles when seller
replies had been sent directly through eBay and later synchronized.

That could leave data such as:

    Buyer message: 2026-07-29
    Seller reply:  2026-07-29

but:

    conversation_sla_history.replied_time = NULL

The Inbox would then continue calculating SLA from July 29 even though the
seller had already replied.

This script reconstructs expected SLA cycles from the authoritative Message
chronology and reconciles conversation_sla_history.

IMPORTANT BUSINESS RULE - OPTION A
===================================

The FIRST unanswered buyer message starts the SLA.

Additional buyer messages received before the seller replies DO NOT restart
or reset the SLA.

Example:

    10:00 Buyer  -> SLA starts at 10:00
    10:15 Buyer  -> same SLA, still 10:00
    10:30 Buyer  -> same SLA, still 10:00
    11:00 Seller -> SLA completes 10:00 -> 11:00

If the buyer later sends another message:

    14:00 Buyer  -> new SLA cycle starts at 14:00


SAFETY
======

Default execution is DRY-RUN ONLY.

Dry run:

    python .\\scripts\\repair_sla_history.py

Apply changes:

    python .\\scripts\\repair_sla_history.py --apply

Repair one conversation only:

    python .\\scripts\\repair_sla_history.py --conversation-id <UUID>

Apply one conversation:

    python .\\scripts\\repair_sla_history.py --conversation-id <UUID> --apply


BACKUP
======

Before --apply modifies SLA history, the current rows being affected are
written to:

    scripts/backups/sla_history_backup_<timestamp>.json

This backup is for debugging/recovery reference and makes historical changes
auditable.


WHAT THIS SCRIPT DOES NOT CHANGE
================================

- Message rows
- Conversation assignments
- Categories
- Conversation notes
- eBay data
- Message classifications
- Conversation status

Only conversation_sla_history is reconciled.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from uuid import UUID


# ---------------------------------------------------------------------------
# Project import path
# ---------------------------------------------------------------------------
#
# This maintenance script lives in:
#
#     backend/scripts/repair_sla_history.py
#
# while the application package lives in:
#
#     backend/app/
#
# When Python executes a script directly, it places the script directory
# (backend/scripts) on sys.path rather than its parent backend directory.
# Without this explicit path setup imports such as:
#
#     from app.db.session import SessionLocal
#
# fail with:
#
#     ModuleNotFoundError: No module named 'app'
#
# Resolve the backend directory relative to this file so the script works
# regardless of the PowerShell/current working directory used to launch it.
BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import SessionLocal
from app.models.conversation import (
    Conversation,
    ConversationSLAHistory,
    Message,
    MessageSenderType,
)
from app.services.sla_service import SLAService


# ---------------------------------------------------------------------------
# Data structures used only inside this repair utility
# ---------------------------------------------------------------------------


@dataclass
class ExpectedSLACycle:
    """
    SLA cycle reconstructed from Message chronology.

    buyer_message_time:
        Timestamp of the FIRST unanswered buyer message.

    reply_message:
        First seller/agent reply after that buyer message.

        None means the buyer is still awaiting a seller response.
    """

    cycle_number: int
    buyer_message_time: datetime
    reply_message: Message | None


@dataclass
class RepairStats:
    """Counters printed at the end of the repair run."""

    conversations_scanned: int = 0
    conversations_with_expected_sla: int = 0
    conversations_changed: int = 0

    cycles_expected: int = 0
    cycles_created: int = 0
    cycles_updated: int = 0
    cycles_deleted: int = 0

    conversations_skipped: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_datetime(value: datetime | None) -> datetime | None:
    """
    Normalize timestamps to timezone-aware UTC.

    PostgreSQL DateTime(timezone=True) should already return timezone-aware
    values. The naive fallback is kept for defensive handling of legacy data.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def datetimes_equal(
    first: datetime | None,
    second: datetime | None,
    tolerance_seconds: float = 1.0,
) -> bool:
    """
    Compare timestamps with a small tolerance.

    Some provider/database timestamp representations can differ by fractions
    of a second. A one-second tolerance prevents harmless precision differences
    from being reported as SLA corruption.
    """
    first = normalize_datetime(first)
    second = normalize_datetime(second)

    if first is None or second is None:
        return first is second

    return (
        abs((first - second).total_seconds())
        <= tolerance_seconds
    )


def parse_actor_id(message: Message | None) -> UUID | None:
    """
    Recover the internal helpdesk user UUID from an outbound message.

    Replies sent through EbayReplyService store:

        raw_payload["actor_id"]

    Replies made directly through ebay.com / eBay app normally do not contain
    an internal actor_id.

    In that situation None is correct. We must never invent PMS attribution.
    """
    if message is None:
        return None

    payload = (
        message.raw_payload
        if isinstance(message.raw_payload, dict)
        else {}
    )

    raw_actor_id = payload.get("actor_id")

    if not raw_actor_id:
        return None

    try:
        return UUID(str(raw_actor_id))
    except (TypeError, ValueError):
        return None


def is_customer_message(message: Message) -> bool:
    """
    Return True only for real inbound buyer/customer messages.

    Provider/system notifications must never start an SLA cycle.
    """
    return bool(
        message.is_inbound
        and message.sender_type == MessageSenderType.CUSTOMER
    )


def is_agent_reply(message: Message) -> bool:
    """
    Return True only for seller/agent replies.

    PROVIDER messages are intentionally excluded even though they may also be
    stored as non-inbound messages.
    """
    return bool(
        not message.is_inbound
        and message.sender_type == MessageSenderType.AGENT
    )


def build_expected_cycles(
    conversation: Conversation,
) -> list[ExpectedSLACycle]:
    """
    Reconstruct SLA history solely from stored Message chronology.

    OPTION A IS PRESERVED:

    - First buyer message starts the cycle.
    - Further buyer messages before seller response do nothing.
    - First seller response completes the cycle.
    - Next buyer message after completion starts a new cycle.

    System/provider messages do not affect SLA.
    """
    messages = sorted(
        conversation.messages,
        key=lambda message: (
            normalize_datetime(message.sent_at)
            or datetime.min.replace(tzinfo=UTC),
            str(message.id),
        ),
    )

    expected: list[ExpectedSLACycle] = []

    active_buyer_time: datetime | None = None

    for message in messages:
        sent_at = normalize_datetime(message.sent_at)

        if sent_at is None:
            # Message.sent_at is non-nullable according to the model, but this
            # guard makes the repair script safe against unexpected legacy data.
            continue

        if is_customer_message(message):
            if active_buyer_time is None:
                # OPTION A:
                # Only the FIRST unanswered buyer message starts the SLA.
                active_buyer_time = sent_at

            # Additional customer messages while active_buyer_time exists are
            # deliberately ignored. They must NOT reset the SLA timer.
            continue

        if is_agent_reply(message):
            if active_buyer_time is None:
                # Seller message without an unanswered buyer message.
                # It cannot complete any SLA cycle.
                continue

            # Defensive chronology check.
            #
            # A seller message older than/equal to the buyer message cannot be
            # treated as a response to that buyer message.
            if sent_at <= active_buyer_time:
                continue

            expected.append(
                ExpectedSLACycle(
                    cycle_number=len(expected) + 1,
                    buyer_message_time=active_buyer_time,
                    reply_message=message,
                )
            )

            # The seller has answered. The next buyer message, if any, begins
            # a brand-new SLA cycle.
            active_buyer_time = None

    if active_buyer_time is not None:
        # Conversation currently has an unanswered buyer message.
        expected.append(
            ExpectedSLACycle(
                cycle_number=len(expected) + 1,
                buyer_message_time=active_buyer_time,
                reply_message=None,
            )
        )

    return expected


def serialize_existing_row(
    row: ConversationSLAHistory,
) -> dict:
    """Convert one existing SLA row into JSON-safe backup data."""
    return {
        "id": str(row.id),
        "conversation_id": str(row.conversation_id),
        "cycle_number": row.cycle_number,
        "buyer_message_time": (
            row.buyer_message_time.isoformat()
            if row.buyer_message_time
            else None
        ),
        "replied_time": (
            row.replied_time.isoformat()
            if row.replied_time
            else None
        ),
        "replied_by": (
            str(row.replied_by)
            if row.replied_by
            else None
        ),
        "response_duration_seconds": (
            row.response_duration_seconds
        ),
        "sla_met": row.sla_met,
        "created_at": (
            row.created_at.isoformat()
            if row.created_at
            else None
        ),
    }


def existing_row_matches_expected(
    row: ConversationSLAHistory,
    expected: ExpectedSLACycle,
    *,
    target_seconds: int,
) -> bool:
    """
    Determine whether an existing SLA row already matches reconstructed truth.

    replied_by is intentionally handled separately because valid historical
    attribution may need to be preserved even when the message raw_payload no
    longer contains actor_id.
    """
    if row.cycle_number != expected.cycle_number:
        return False

    if not datetimes_equal(
        row.buyer_message_time,
        expected.buyer_message_time,
    ):
        return False

    expected_reply_time = (
        expected.reply_message.sent_at
        if expected.reply_message
        else None
    )

    if not datetimes_equal(
        row.replied_time,
        expected_reply_time,
    ):
        return False

    if expected.reply_message is None:
        return (
            row.response_duration_seconds is None
            and row.sla_met is None
        )

    duration = SLAService.business_seconds_between(
        expected.buyer_message_time,
        expected_reply_time,
    )

    expected_sla_met = duration <= target_seconds

    return (
        row.response_duration_seconds == duration
        and row.sla_met == expected_sla_met
    )


def determine_replied_by(
    expected: ExpectedSLACycle,
    existing_row: ConversationSLAHistory | None,
) -> UUID | None:
    """
    Determine internal user attribution for a repaired completed cycle.

    Priority:

    1. actor_id stored on the actual outbound helpdesk Message.
    2. Existing valid replied_by from the corresponding SLA row.
    3. None for replies made externally through eBay.

    This protects existing PMS attribution while ensuring external replies are
    never falsely assigned to an internal user.
    """
    if expected.reply_message is None:
        return None

    actor_id = parse_actor_id(
        expected.reply_message
    )

    if actor_id is not None:
        return actor_id

    if (
        existing_row is not None
        and existing_row.replied_by is not None
        and datetimes_equal(
            existing_row.replied_time,
            expected.reply_message.sent_at,
        )
    ):
        return existing_row.replied_by

    return None


# ---------------------------------------------------------------------------
# Database loading
# ---------------------------------------------------------------------------


def load_conversations(
    db: Session,
    conversation_id: UUID | None,
) -> list[Conversation]:
    """
    Load conversations with all relationships needed by reconciliation.

    Messages and SLA history are eager-loaded to avoid lazy N+1 queries.
    Category is loaded because the existing SLA implementation obtains its
    target from conversation.category.sla_hours.
    """
    statement = (
        select(Conversation)
        .options(
            selectinload(Conversation.messages),
            selectinload(Conversation.sla_history),
            joinedload(Conversation.category),
        )
        .order_by(
            Conversation.created_at.asc(),
            Conversation.id.asc(),
        )
    )

    if conversation_id:
        statement = statement.where(
            Conversation.id == conversation_id
        )

    return list(
        db.scalars(statement).unique()
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile_conversation(
    db: Session,
    conversation: Conversation,
    *,
    apply: bool,
    stats: RepairStats,
    backup_rows: list[dict],
) -> None:
    """
    Compare expected SLA chronology against stored conversation_sla_history.

    Existing rows are reused by cycle number whenever possible. This avoids
    unnecessarily deleting/recreating valid rows and helps preserve historical
    IDs and internal user attribution.
    """
    stats.conversations_scanned += 1

    # FROM_EBAY conversations represent eBay system notifications rather than
    # buyer support exchanges. They must not be reconstructed into customer SLA
    # cycles by this utility.
    if (
        conversation.provider_conversation_type
        or ""
    ).upper() == "FROM_EBAY":
        stats.conversations_skipped += 1
        return

    expected_cycles = build_expected_cycles(
        conversation
    )

    existing_rows = sorted(
        conversation.sla_history,
        key=lambda row: row.cycle_number or 0,
    )

    if expected_cycles:
        stats.conversations_with_expected_sla += 1

    stats.cycles_expected += len(expected_cycles)

    existing_by_number = {
        row.cycle_number: row
        for row in existing_rows
    }

    service = SLAService(db)

    target_seconds = service.target_seconds_for(
        conversation
    )

    conversation_changes: list[str] = []

    # ------------------------------------------------------------------
    # Reconcile expected cycles
    # ------------------------------------------------------------------
    for expected in expected_cycles:
        existing = existing_by_number.get(
            expected.cycle_number
        )

        reply_time = (
            normalize_datetime(
                expected.reply_message.sent_at
            )
            if expected.reply_message
            else None
        )

        duration = None
        sla_met = None

        if reply_time is not None:
            duration = service.business_seconds_between(
                expected.buyer_message_time,
                reply_time,
            )

            sla_met = duration <= target_seconds

        replied_by = determine_replied_by(
            expected,
            existing,
        )

        if existing is None:
            conversation_changes.append(
                (
                    f"CREATE cycle {expected.cycle_number}: "
                    f"buyer={expected.buyer_message_time.isoformat()} "
                    f"reply={reply_time.isoformat() if reply_time else 'ACTIVE'}"
                )
            )

            if apply:
                new_row = ConversationSLAHistory(
                    conversation_id=conversation.id,
                    cycle_number=expected.cycle_number,
                    buyer_message_time=expected.buyer_message_time,
                    replied_time=reply_time,
                    replied_by=replied_by,
                    response_duration_seconds=duration,
                    sla_met=sla_met,
                )

                db.add(new_row)

            stats.cycles_created += 1
            continue

        row_is_correct = existing_row_matches_expected(
            existing,
            expected,
            target_seconds=target_seconds,
        )

        # Even when chronology/duration matches, actor attribution may be
        # recoverable from the outbound message raw_payload.
        actor_needs_update = (
            replied_by is not None
            and existing.replied_by != replied_by
        )

        if row_is_correct and not actor_needs_update:
            continue

        conversation_changes.append(
            (
                f"UPDATE cycle {expected.cycle_number}: "
                f"buyer "
                f"{existing.buyer_message_time.isoformat()} "
                f"-> {expected.buyer_message_time.isoformat()}, "
                f"reply "
                f"{existing.replied_time.isoformat() if existing.replied_time else 'NULL'} "
                f"-> {reply_time.isoformat() if reply_time else 'ACTIVE'}"
            )
        )

        if apply:
            # Preserve the existing row ID but make its SLA values match the
            # authoritative message chronology.
            existing.buyer_message_time = (
                expected.buyer_message_time
            )
            existing.replied_time = reply_time
            existing.response_duration_seconds = (
                duration
            )
            existing.sla_met = sla_met
            existing.replied_by = replied_by

        stats.cycles_updated += 1

    # ------------------------------------------------------------------
    # Remove stale/extra SLA rows
    # ------------------------------------------------------------------
    #
    # Example:
    # Existing DB contains cycles 1..7 but message chronology only produces
    # cycles 1..5. Cycles 6 and 7 cannot represent valid first-response cycles
    # and are therefore stale historical artifacts.
    expected_numbers = {
        cycle.cycle_number
        for cycle in expected_cycles
    }

    extra_rows = [
        row
        for row in existing_rows
        if row.cycle_number not in expected_numbers
    ]

    for row in extra_rows:
        conversation_changes.append(
            (
                f"DELETE extra cycle {row.cycle_number}: "
                f"buyer={row.buyer_message_time.isoformat()}"
            )
        )

        if apply:
            db.delete(row)

        stats.cycles_deleted += 1

    if not conversation_changes:
        return

    stats.conversations_changed += 1

    # Back up all current SLA rows for any conversation that will be modified.
    backup_rows.extend(
        serialize_existing_row(row)
        for row in existing_rows
    )

    print()
    print(
        "=" * 90
    )
    print(
        f"Conversation: {conversation.id}"
    )
    print(
        f"Buyer:        {conversation.buyer_identifier or '-'}"
    )
    print(
        f"Subject:      {conversation.subject or '-'}"
    )
    print(
        f"Messages:     {len(conversation.messages)}"
    )
    print(
        f"Existing SLA: {len(existing_rows)}"
    )
    print(
        f"Expected SLA: {len(expected_cycles)}"
    )
    print(
        "-" * 90
    )

    for change in conversation_changes:
        print(
            f"  {change}"
        )


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def write_backup(
    backup_rows: Iterable[dict],
) -> Path | None:
    """
    Save pre-repair SLA rows to a timestamped JSON file.

    Returns None when nothing is being modified.
    """
    rows = list(backup_rows)

    if not rows:
        return None

    script_directory = Path(__file__).resolve().parent

    backup_directory = (
        script_directory / "backups"
    )

    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        UTC
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_path = (
        backup_directory
        / f"sla_history_backup_{timestamp}.json"
    )

    backup_path.write_text(
        json.dumps(
            rows,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return backup_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile conversation_sla_history from stored "
            "buyer/agent message chronology."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually write repairs to the database. "
            "Without this flag the script is dry-run only."
        ),
    )

    parser.add_argument(
        "--conversation-id",
        type=UUID,
        default=None,
        help=(
            "Repair/analyze only one conversation UUID. "
            "Recommended for first validation."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    mode = (
        "APPLY"
        if args.apply
        else "DRY RUN"
    )

    print()
    print(
        "=" * 90
    )
    print(
        "SLA HISTORY RECONCILIATION"
    )
    print(
        "=" * 90
    )
    print(
        f"Mode: {mode}"
    )

    if args.conversation_id:
        print(
            f"Conversation: {args.conversation_id}"
        )
    else:
        print(
            "Conversation: ALL"
        )

    if not args.apply:
        print()
        print(
            "No database changes will be committed."
        )

    stats = RepairStats()
    backup_rows: list[dict] = []

    with SessionLocal() as db:
        try:
            conversations = load_conversations(
                db,
                args.conversation_id,
            )

            if (
                args.conversation_id
                and not conversations
            ):
                print()
                print(
                    "Conversation not found."
                )
                return 1

            print()
            print(
                f"Loaded {len(conversations)} conversation(s)."
            )

            for conversation in conversations:
                reconcile_conversation(
                    db,
                    conversation,
                    apply=args.apply,
                    stats=stats,
                    backup_rows=backup_rows,
                )

            if args.apply:
                # Write the backup BEFORE committing any modifications.
                backup_path = write_backup(
                    backup_rows
                )

                if backup_path:
                    print()
                    print(
                        f"Backup created: {backup_path}"
                    )

                db.commit()

                print()
                print(
                    "Database transaction committed successfully."
                )

            else:
                # Defensive rollback ensures accidental ORM modifications made
                # during future script maintenance cannot leak from dry-run.
                db.rollback()

        except Exception:
            db.rollback()

            print()
            print(
                "ERROR: transaction rolled back."
            )

            raise

    print()
    print(
        "=" * 90
    )
    print(
        "SUMMARY"
    )
    print(
        "=" * 90
    )
    print(
        f"Conversations scanned:           {stats.conversations_scanned}"
    )
    print(
        f"Conversations skipped:           {stats.conversations_skipped}"
    )
    print(
        f"With reconstructed SLA cycles:   "
        f"{stats.conversations_with_expected_sla}"
    )
    print(
        f"Conversations requiring changes: {stats.conversations_changed}"
    )
    print(
        f"Expected SLA cycles:             {stats.cycles_expected}"
    )
    print(
        f"Cycles to create:                {stats.cycles_created}"
    )
    print(
        f"Cycles to update:                {stats.cycles_updated}"
    )
    print(
        f"Extra cycles to delete:          {stats.cycles_deleted}"
    )

    if not args.apply:
        print()
        print(
            "DRY RUN COMPLETE - nothing was changed."
        )
        print(
            "Review the output carefully before running with --apply."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())