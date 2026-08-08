from datetime import UTC, datetime
from uuid import UUID
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.conversation import Conversation, ConversationCategoryHistory, ConversationStatus, ConversationStatusHistory
from app.repositories.assignment_repository import AssignmentRepository
from app.repositories.conversation_category_history_repository import ConversationCategoryHistoryRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_status_history_repository import ConversationStatusHistoryRepository
from app.services.sla_service import SLAService

logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ConversationRepository(db)
        self.assignment_repository = AssignmentRepository(db)
        self.status_history_repository = ConversationStatusHistoryRepository(db)
        self.category_history_repository = ConversationCategoryHistoryRepository(db)

    def list_conversations(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
        status: ConversationStatus | None = None,
        provider: str | None = None,
        conversation_type: str | None = None,
        provider_account_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        category_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sla_due_within_hours: int | None = None,
    ) -> list[Conversation]:
        """Return conversations matching the requested filters."""
        if sla_due_within_hours is not None:
            matching_ids = self._near_due_conversation_ids(
                search=search,
                status=status,
                provider=provider,
                conversation_type=conversation_type,
                provider_account_id=provider_account_id,
                assigned_user_id=assigned_user_id,
                category_id=category_id,
                date_from=date_from,
                date_to=date_to,
                within_hours=sla_due_within_hours,
            )

            if not matching_ids:
                return []

            return self.repository.list(
                limit=limit,
                offset=offset,
                search=search,
                status=status,
                provider=provider,
                conversation_type=conversation_type,
                provider_account_id=provider_account_id,
                assigned_user_id=assigned_user_id,
                category_id=category_id,
                date_from=date_from,
                date_to=date_to,
                conversation_ids=matching_ids,
            )

        return self.repository.list(
            limit=limit,
            offset=offset,
            search=search,
            status=status,
            provider=provider,
            conversation_type=conversation_type,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
            date_from=date_from,
            date_to=date_to,
        )

    def count_conversations(
        self,
        *,
        search: str | None = None,
        status: ConversationStatus | None = None,
        provider: str | None = None,
        conversation_type: str | None = None,
        provider_account_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        category_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sla_due_within_hours: int | None = None,
    ) -> int:
        """Return the filtered conversation total for pagination and dashboards."""
        if sla_due_within_hours is not None:
            return len(
                self._near_due_conversation_ids(
                    search=search,
                    status=status,
                    provider=provider,
                    conversation_type=conversation_type,
                    provider_account_id=provider_account_id,
                    assigned_user_id=assigned_user_id,
                    category_id=category_id,
                    date_from=date_from,
                    date_to=date_to,
                    within_hours=sla_due_within_hours,
                )
            )

        return self.repository.count(
            search=search,
            status=status,
            provider=provider,
            conversation_type=conversation_type,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
            date_from=date_from,
            date_to=date_to,
        )

    def _near_due_conversation_ids(
        self,
        *,
        search: str | None = None,
        status: ConversationStatus | None = None,
        provider: str | None = None,
        conversation_type: str | None = None,
        provider_account_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        category_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        within_hours: int,
    ) -> list[UUID]:
        """
        Return ONLY unresolved SLA conversations with at most the requested
        BUSINESS time remaining before breach.

        Message chronology is authoritative here. This prevents a stale active
        SLA-history row from causing a conversation that already received a
        seller reply to appear in the Near Due queue.

        Option A is preserved:
        - first unanswered buyer message starts the cycle;
        - additional buyer messages do not restart it;
        - first seller reply closes that cycle;
        - a later buyer message starts a new cycle.
        """
        candidates = self.repository.list_sla_candidates(
            search=search,
            status=status,
            provider=provider,
            conversation_type=conversation_type,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
            date_from=date_from,
            date_to=date_to,
        )

        if not candidates:
            return []

        now = datetime.now(UTC)
        warning_seconds = int(within_hours * 3600)
        sla_service = SLAService(None)
        matching_ids: list[UUID] = []

        for conversation in candidates:
            buyer_message = None
            reply_message = None

            # Reconstruct the latest SLA cycle from actual message history.
            # This mirrors the inbox SLA snapshot rules and prevents already
            # responded conversations from leaking into the Near Due filter.
            for message in sorted(
                conversation.messages,
                key=lambda row: row.sent_at,
            ):
                sender_type = getattr(
                    getattr(message, "sender_type", None),
                    "value",
                    getattr(message, "sender_type", None),
                )
                is_seller_reply = (
                    sender_type == "AGENT"
                    or not message.is_inbound
                )

                if is_seller_reply:
                    if (
                        buyer_message is not None
                        and reply_message is None
                    ):
                        reply_message = message
                    continue

                if message.is_inbound:
                    if (
                        buyer_message is None
                        or reply_message is not None
                    ):
                        buyer_message = message
                        reply_message = None

            # Near Due must contain ONLY an unanswered buyer SLA cycle.
            if buyer_message is None or reply_message is not None:
                continue

            target_seconds = sla_service.target_seconds_for(
                conversation
            )
            elapsed_seconds = sla_service.business_seconds_between(
                buyer_message.sent_at,
                now,
            )
            remaining_seconds = (
                target_seconds - elapsed_seconds
            )

            # Near Due includes BOTH:
            # 1. unanswered conversations with <= warning window remaining;
            # 2. unanswered conversations that are already overdue.
            #
            # A negative value means the SLA has been breached by that many
            # business seconds. If there are no matches, matching_ids stays
            # empty and the list endpoint returns an empty result.
            if remaining_seconds <= warning_seconds:
                matching_ids.append(conversation.id)

        return matching_ids

    def get_conversation(
        self,
        conversation_id: UUID,
    ) -> Conversation:
        """Return one conversation by ID."""
        conversation = self.repository.get_by_id(
            conversation_id,
        )

        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Conversation not found')

        return conversation

    def mark_read(self, conversation: Conversation) -> Conversation:
        """Clear local unread indicators after an agent opens a conversation."""
        conversation.unread_count = 0
        for message in conversation.messages:
            if message.is_inbound and message.read_status is not True:
                message.read_status = True
        self.db.commit()
        self.db.refresh(conversation)
        return self.get_conversation(conversation.id)

    def get_current_assignee_id(self, conversation_id: UUID) -> UUID | None:
        assignment = self.assignment_repository.get_current_assignment(conversation_id)
        return assignment.assigned_to if assignment else None

    def update_status(
        self,
        *,
        conversation_id: UUID,
        new_status: ConversationStatus,
        changed_by: UUID,
        note: str | None = None,
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        old_status = conversation.status
        conversation.status = new_status
        self.status_history_repository.add(
            ConversationStatusHistory(
                conversation_id=conversation.id,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                note=note.strip() if note else None,
            )
        )
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_category(
        self,
        *,
        conversation_id: UUID,
        category_id: UUID | None,
        changed_by: UUID,
        note: str | None = None,
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        if category_id and not self.db.get(Category, category_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Category not found')

        old_category_id = conversation.category_id
        conversation.category_id = category_id
        conversation.category_manually_selected = True
        self.category_history_repository.add(
            ConversationCategoryHistory(
                conversation_id=conversation.id,
                old_category_id=old_category_id,
                new_category_id=category_id,
                changed_by=changed_by,
                note=note.strip() if note else None,
            )
        )
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
