"""Conversation lifecycle and immutable first-response SLA management."""

from datetime import datetime
from uuid import UUID

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
        active = self.db.scalar(select(ConversationSLAHistory).where(
            ConversationSLAHistory.conversation_id == conversation.id,
            ConversationSLAHistory.replied_time.is_(None),
        ))
        if active:
            return active
        cycle_number = (self.db.scalar(select(func.max(ConversationSLAHistory.cycle_number)).where(
            ConversationSLAHistory.conversation_id == conversation.id,
        )) or 0) + 1
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
            duration = max(0, int((replied_at - cycle.buyer_message_time).total_seconds()))
            cycle.replied_time = replied_at
            cycle.replied_by = actor_id
            cycle.response_duration_seconds = duration
            cycle.sla_met = duration <= self.target_seconds
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
