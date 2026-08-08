"""Conversation lifecycle and immutable first-response SLA management."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import (
    Conversation,
    ConversationSLAHistory,
    ConversationStatus,
    ConversationStatusHistory,
)


class SLAService:
    """
    Manage conversation SLA cycles.

    SLA business lifecycle:

    1. The first unanswered buyer message starts an SLA cycle.
    2. Additional buyer messages before a seller reply DO NOT restart the SLA.
       This intentionally preserves "Option A": SLA always starts from the
       first unanswered buyer message.
    3. The first valid seller reply completes the active SLA cycle.
    4. A later buyer message starts a brand-new cycle.
    5. Completed cycles are historical records and must not be recalculated.

    SLA completion can happen from two sources:

    - Helpdesk reply:
      The internal user UUID is known and stored in replied_by.

    - Seller reply synchronized from eBay:
      The response time is known, but the internal user may be unknown.
      In that case replied_by remains NULL rather than assigning fake credit.
    """

    IST = ZoneInfo("Asia/Kolkata")
    OFFICE_START = time(9, 30)
    OFFICE_END = time(18, 30)

    def __init__(self, db: Session | None, target_seconds: int = 3600) -> None:
        self.db = db
        self.target_seconds = target_seconds

    @classmethod
    def to_ist(cls, value: datetime) -> datetime:
        """
        Normalize a datetime into Asia/Kolkata.

        Provider timestamps should normally be timezone-aware. If a legacy
        naive timestamp is encountered, UTC is assumed for consistency.
        """
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)

        return value.astimezone(cls.IST)

    @classmethod
    def is_working_day(cls, value: datetime) -> bool:
        """Return False for Sunday; all other days are SLA working days."""
        return cls.to_ist(value).weekday() != 6

    @classmethod
    def next_business_time(cls, value: datetime) -> datetime:
        """
        Move a timestamp to the next valid SLA business instant.

        Business hours:
            09:30 AM - 06:30 PM IST

        Sunday is excluded.
        """
        current = cls.to_ist(value)

        while current.weekday() == 6:
            current = datetime.combine(
                current.date() + timedelta(days=1),
                cls.OFFICE_START,
                tzinfo=cls.IST,
            )

        start = datetime.combine(
            current.date(),
            cls.OFFICE_START,
            tzinfo=cls.IST,
        )
        end = datetime.combine(
            current.date(),
            cls.OFFICE_END,
            tzinfo=cls.IST,
        )

        if current < start:
            return start

        if current >= end:
            current = datetime.combine(
                current.date() + timedelta(days=1),
                cls.OFFICE_START,
                tzinfo=cls.IST,
            )

            while current.weekday() == 6:
                current = datetime.combine(
                    current.date() + timedelta(days=1),
                    cls.OFFICE_START,
                    tzinfo=cls.IST,
                )

            return current

        return current

    @classmethod
    def business_seconds_between(
        cls,
        start: datetime,
        end: datetime,
    ) -> int:
        """
        Calculate SLA elapsed seconds between two timestamps.

        Only working time between 09:30 and 18:30 IST is counted.
        Sunday contributes zero SLA time.
        """
        current = cls.next_business_time(start)
        finish = cls.to_ist(end)

        if finish <= current:
            return 0

        seconds = 0

        while current < finish:
            if current.weekday() == 6:
                current = cls.next_business_time(current)
                continue

            office_end = datetime.combine(
                current.date(),
                cls.OFFICE_END,
                tzinfo=cls.IST,
            )

            segment_end = min(office_end, finish)

            if segment_end > current:
                seconds += int(
                    (segment_end - current).total_seconds()
                )

            current = cls.next_business_time(
                datetime.combine(
                    current.date() + timedelta(days=1),
                    cls.OFFICE_START,
                    tzinfo=cls.IST,
                )
            )

        return seconds

    @classmethod
    def due_at(
        cls,
        start: datetime,
        target_seconds: int,
    ) -> datetime:
        """Return the UTC deadline after adding SLA business seconds."""
        current = cls.next_business_time(start)
        remaining = max(0, int(target_seconds))

        while remaining:
            office_end = datetime.combine(
                current.date(),
                cls.OFFICE_END,
                tzinfo=cls.IST,
            )

            available = max(
                0,
                int((office_end - current).total_seconds()),
            )

            if remaining <= available:
                return (
                    current + timedelta(seconds=remaining)
                ).astimezone(UTC)

            remaining -= available

            current = cls.next_business_time(
                datetime.combine(
                    current.date() + timedelta(days=1),
                    cls.OFFICE_START,
                    tzinfo=cls.IST,
                )
            )

        return current.astimezone(UTC)

    def target_seconds_for(
        self,
        conversation: Conversation,
    ) -> int:
        """
        Return the SLA target configured on the current conversation category.

        Existing fallback behaviour is intentionally preserved.
        """
        sla_hours = getattr(
            getattr(conversation, "category", None),
            "sla_hours",
            None,
        )

        if sla_hours:
            return int(sla_hours * 3600)

        return self.target_seconds

    def start_cycle(
        self,
        conversation: Conversation,
        buyer_message_time: datetime,
    ) -> ConversationSLAHistory:
        """
        Start an SLA cycle for the first unanswered buyer message.

        IMPORTANT BUSINESS RULE - OPTION A:
        If another buyer message arrives while an SLA cycle is already active,
        the active cycle is reused. The SLA timer is NOT reset.

        Example:
            10:00 Buyer message -> SLA starts at 10:00
            10:15 Buyer message -> SLA remains 10:00
            10:30 Buyer message -> SLA remains 10:00
            11:00 Seller reply  -> SLA completes 10:00 -> 11:00
        """
        if self.db is None:
            raise RuntimeError(
                "A database session is required to start an SLA cycle"
            )

        # SQLAlchemy sync jobs may run with autoflush disabled. A new SLA cycle
        # created earlier in the same transaction may therefore not yet be
        # visible through SELECT. Check pending session objects first.
        active = next(
            (
                row
                for row in self.db.new
                if isinstance(row, ConversationSLAHistory)
                and row.conversation_id == conversation.id
                and row.replied_time is None
            ),
            None,
        )

        if active:
            return active

        active = self.db.scalar(
            select(ConversationSLAHistory)
            .where(
                ConversationSLAHistory.conversation_id
                == conversation.id,
                ConversationSLAHistory.replied_time.is_(None),
            )
            .order_by(
                ConversationSLAHistory.cycle_number.desc()
            )
        )

        # Preserve Option A: do not reset the SLA when another buyer message
        # arrives before the seller has replied.
        if active:
            return active

        persisted_max = (
            self.db.scalar(
                select(
                    func.max(
                        ConversationSLAHistory.cycle_number
                    )
                ).where(
                    ConversationSLAHistory.conversation_id
                    == conversation.id
                )
            )
            or 0
        )

        # Include cycles created earlier in the same unflushed sync transaction
        # so cycle numbers remain unique.
        pending_max = max(
            (
                row.cycle_number
                for row in self.db.new
                if isinstance(row, ConversationSLAHistory)
                and row.conversation_id == conversation.id
            ),
            default=0,
        )

        cycle_number = max(
            persisted_max,
            pending_max,
        ) + 1

        cycle = ConversationSLAHistory(
            conversation_id=conversation.id,
            cycle_number=cycle_number,
            buyer_message_time=buyer_message_time,
        )

        self.db.add(cycle)

        # A new unanswered buyer message reopens a previously resolved thread.
        # CLOSED is archival and intentionally remains closed.
        if conversation.status != ConversationStatus.CLOSED:
            conversation.status = ConversationStatus.OPEN

        return cycle

    def complete_after_reply(
        self,
        conversation: Conversation,
        actor_id: UUID | None,
        replied_at: datetime,
    ) -> ConversationSLAHistory | None:
        """
        Complete the currently active SLA cycle.

        actor_id:
            Internal user UUID when the reply was sent through this helpdesk.

            None when the seller reply was discovered during eBay sync and the
            application cannot reliably identify which internal user sent it.

        replied_at:
            Provider/local message timestamp representing the seller response.

        The method deliberately does NOT invent agent attribution for replies
        sent outside the helpdesk.
        """
        if self.db is None:
            raise RuntimeError(
                "A database session is required to complete an SLA cycle"
            )

        if conversation.status == ConversationStatus.CLOSED:
            return None

        # Only a seller message that occurred AFTER the buyer message can close
        # that buyer's SLA. This protects against historical/out-of-order eBay
        # payloads accidentally closing a newer SLA cycle.
        cycle = self.db.scalar(
            select(ConversationSLAHistory)
            .where(
                ConversationSLAHistory.conversation_id
                == conversation.id,
                ConversationSLAHistory.replied_time.is_(None),
                ConversationSLAHistory.buyer_message_time
                < replied_at,
            )
            .order_by(
                ConversationSLAHistory.cycle_number.desc()
            )
        )

        if not cycle:
            # Seller messages may legitimately exist without an unanswered
            # buyer message. In that situation there is no SLA to complete.
            return None

        duration = self.business_seconds_between(
            cycle.buyer_message_time,
            replied_at,
        )

        target_seconds = self.target_seconds_for(
            conversation
        )

        cycle.replied_time = replied_at
        cycle.replied_by = actor_id
        cycle.response_duration_seconds = duration
        cycle.sla_met = duration <= target_seconds

        old_status = conversation.status
        conversation.status = ConversationStatus.RESOLVED

        if old_status != ConversationStatus.RESOLVED:
            self.db.add(
                ConversationStatusHistory(
                    conversation_id=conversation.id,
                    old_status=old_status,
                    new_status=ConversationStatus.RESOLVED,
                    changed_by=actor_id,
                    note=(
                        "Automatically resolved after eBay confirmed "
                        "reply delivery."
                        if actor_id is not None
                        else
                        "Automatically resolved after a synchronized "
                        "seller reply was detected on eBay."
                    ),
                )
            )

        return cycle