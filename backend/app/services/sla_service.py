"""Conversation lifecycle and immutable first-response SLA management."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationSLAHistory, ConversationStatus, ConversationStatusHistory


class SLAService:
    """
    Manage SLA cycles and the automatic post-reply lifecycle transition.

    Responsibilities include opening one cycle for each unanswered buyer
    message and completing only the active cycle after confirmed delivery.
    Completed measurements are never recalculated or overwritten.
    """

    def __init__(self, db: Session, target_seconds: int = 3600) -> None:
        """Create the service with a database session and response target."""
        self.db = db
        self.target_seconds = target_seconds

    IST = ZoneInfo("Asia/Kolkata")
    OFFICE_START = time(9, 30)
    OFFICE_END = time(18, 30)

    @classmethod
    def to_ist(cls, value: datetime) -> datetime:
        """Normalize timestamps to IST for SLA math."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(cls.IST)

    @classmethod
    def is_working_day(cls, value: datetime) -> bool:
        return cls.to_ist(value).weekday() != 6

    @classmethod
    def next_business_time(cls, value: datetime) -> datetime:
        current = cls.to_ist(value)
        while current.weekday() == 6:
            current = datetime.combine(current.date() + timedelta(days=1), cls.OFFICE_START, tzinfo=cls.IST)
        start = datetime.combine(current.date(), cls.OFFICE_START, tzinfo=cls.IST)
        end = datetime.combine(current.date(), cls.OFFICE_END, tzinfo=cls.IST)
        if current < start:
            return start
        if current >= end:
            current = datetime.combine(current.date() + timedelta(days=1), cls.OFFICE_START, tzinfo=cls.IST)
            while current.weekday() == 6:
                current = datetime.combine(current.date() + timedelta(days=1), cls.OFFICE_START, tzinfo=cls.IST)
            return current
        return current

    @classmethod
    def business_seconds_between(cls, start: datetime, end: datetime) -> int:
        """Count only 9:30 AM-6:30 PM IST office time, excluding Sundays."""
        current = cls.next_business_time(start)
        finish = cls.to_ist(end)
        if finish <= current:
            return 0

        seconds = 0
        while current < finish:
            if current.weekday() == 6:
                current = cls.next_business_time(current)
                continue
            office_end = datetime.combine(current.date(), cls.OFFICE_END, tzinfo=cls.IST)
            segment_end = min(office_end, finish)
            if segment_end > current:
                seconds += int((segment_end - current).total_seconds())
            current = cls.next_business_time(datetime.combine(current.date() + timedelta(days=1), cls.OFFICE_START, tzinfo=cls.IST))
        return seconds

    @classmethod
    def due_at(cls, start: datetime, target_seconds: int) -> datetime:
        """Return the deadline after adding business seconds to a buyer message."""
        current = cls.next_business_time(start)
        remaining = max(0, int(target_seconds))
        while remaining:
            office_end = datetime.combine(current.date(), cls.OFFICE_END, tzinfo=cls.IST)
            available = max(0, int((office_end - current).total_seconds()))
            if remaining <= available:
                return (current + timedelta(seconds=remaining)).astimezone(UTC)
            remaining -= available
            current = cls.next_business_time(datetime.combine(current.date() + timedelta(days=1), cls.OFFICE_START, tzinfo=cls.IST))
        return current.astimezone(UTC)

    def target_seconds_for(self, conversation: Conversation) -> int:
        sla_hours = getattr(getattr(conversation, "category", None), "sla_hours", None)
        if sla_hours:
            return int(sla_hours * 3600)
        return self.target_seconds

    def start_cycle(self, conversation: Conversation, buyer_message_time: datetime) -> ConversationSLAHistory:
        """
        Start a new SLA cycle when no unanswered cycle already exists.

        Args:
            conversation: Conversation receiving a buyer message.
            buyer_message_time: Provider timestamp used as the SLA origin.

        Returns:
            The existing active cycle or the newly created history row.

        Side Effects:
            Adds an SLA history row and reopens non-closed conversations.

        Business Rules:
            Duplicate sync deliveries must not create duplicate active cycles;
            CLOSED is archival and is never reopened automatically.
        """
        # Sync sessions disable autoflush for performance. A cycle added earlier
        # in this message batch therefore is not visible to the SELECT below yet.
        # Check the session identity set first so every unanswered inbound message
        # in the same batch reuses that pending cycle.
        active = next((
            row for row in self.db.new
            if isinstance(row, ConversationSLAHistory)
            and row.conversation_id == conversation.id
            and row.replied_time is None
        ), None)
        if active:
            return active

        active = self.db.scalar(select(ConversationSLAHistory).where(
            ConversationSLAHistory.conversation_id == conversation.id,
            ConversationSLAHistory.replied_time.is_(None),
        ))
        if active:
            return active
        persisted_max = self.db.scalar(select(func.max(ConversationSLAHistory.cycle_number)).where(
            ConversationSLAHistory.conversation_id == conversation.id,
        )) or 0
        pending_max = max((
            row.cycle_number for row in self.db.new
            if isinstance(row, ConversationSLAHistory)
            and row.conversation_id == conversation.id
        ), default=0)
        cycle_number = max(persisted_max, pending_max) + 1
        cycle = ConversationSLAHistory(
            conversation_id=conversation.id,
            cycle_number=cycle_number,
            buyer_message_time=buyer_message_time,
        )
        self.db.add(cycle)
        if conversation.status != ConversationStatus.CLOSED:
            conversation.status = ConversationStatus.OPEN
        return cycle

    def complete_after_reply(self, conversation: Conversation, actor_id: UUID, replied_at: datetime) -> ConversationSLAHistory | None:
        """
        Freeze the active SLA and resolve after eBay accepts an agent reply.

        Args:
            conversation: Conversation whose reply was delivered.
            actor_id: Agent responsible for the successful reply.
            replied_at: Confirmed local reply timestamp.

        Returns:
            Completed SLA row, or None for legacy threads without an active cycle.

        Side Effects:
            Updates the active SLA row, conversation status, and status history.

        Business Rules:
            Only the first successful response completes a cycle. CLOSED threads
            remain immutable and cannot be resolved by a reply attempt.
        """
        if conversation.status == ConversationStatus.CLOSED:
            return None
        cycle = self.db.scalar(select(ConversationSLAHistory).where(
            ConversationSLAHistory.conversation_id == conversation.id,
            ConversationSLAHistory.replied_time.is_(None),
        ).order_by(ConversationSLAHistory.cycle_number.desc()))
        if cycle:
            duration = self.business_seconds_between(cycle.buyer_message_time, replied_at)
            target_seconds = self.target_seconds_for(conversation)
            cycle.replied_time = replied_at
            cycle.replied_by = actor_id
            cycle.response_duration_seconds = duration
            cycle.sla_met = duration <= target_seconds
        old_status = conversation.status
        conversation.status = ConversationStatus.RESOLVED
        if old_status != ConversationStatus.RESOLVED:
            self.db.add(ConversationStatusHistory(
                conversation_id=conversation.id,
                old_status=old_status,
                new_status=ConversationStatus.RESOLVED,
                changed_by=actor_id,
                note='Automatically resolved after eBay confirmed reply delivery.',
            ))
        return cycle
