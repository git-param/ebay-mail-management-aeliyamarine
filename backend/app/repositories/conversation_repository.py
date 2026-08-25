from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from app.models.category import Category
from app.models.conversation import (
    Conversation,
    ConversationAssignment,
    ConversationNote,
    ConversationStatus,
    Message,
    MessageAttachment,
)


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(
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
        conversation_ids: list[UUID] | None = None,
    ) -> list[Conversation]:
        """
        List conversations matching inbox filters.

        Related data required by row serialization is eagerly loaded here so
        the serializer does not cause per-conversation lazy database queries.
        """
        statement = (
            self._filtered_statement(
                search=search,
                status=status,
                provider=provider,
                conversation_type=conversation_type,
                provider_account_id=provider_account_id,
                assigned_user_id=assigned_user_id,
                category_id=category_id,
                date_from=date_from,
                date_to=date_to,
                conversation_ids=conversation_ids,
            )
            .options(
                selectinload(
                    Conversation.assignments
                ).joinedload(
                    ConversationAssignment.assignee
                ),
                selectinload(
                    Conversation.assignments
                ).joinedload(
                    ConversationAssignment.assigner
                ),
                selectinload(
                    Conversation.messages
                ).selectinload(
                    Message.attachments
                ),

                # SLA snapshot serialization accesses conversation.sla_history.
                # Eager loading prevents a possible N+1 query pattern where
                # each inbox row performs a separate SLA history SELECT.
                selectinload(
                    Conversation.sla_history
                ),

                joinedload(
                    Conversation.category
                ),
            )
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
            )
        )

        if offset:
            statement = statement.offset(offset)

        if limit:
            statement = statement.limit(limit)

        return list(self.db.scalars(statement))

    def count(
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
    ) -> int:
        """Count conversations using the same filters as the list endpoint."""
        statement = self._filtered_statement(
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

        return int(
            self.db.scalar(
                select(func.count()).select_from(
                    statement.subquery()
                )
            )
            or 0
        )

    def list_sla_candidates(
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
    ) -> list[Conversation]:
        """
        Load only the relationships required to evaluate a Near Due SLA filter.

        This avoids loading complete message/attachment histories for every
        inbox conversation before the two-hour SLA warning window is applied.
        """
        statement = (
            self._filtered_statement(
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
            .options(
                # Actual message chronology is required to confirm that the
                # latest buyer SLA cycle is still unanswered. Loading only
                # SLA history can include stale active cycles after a reply.
                selectinload(Conversation.messages),
                selectinload(Conversation.sla_history),
                joinedload(Conversation.category),
            )
        )

        return list(self.db.scalars(statement))

    def get_by_id(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        """
        Return one fully loaded conversation.

        SLA history is explicitly loaded because detail serialization uses the
        same SLA snapshot logic as the inbox list.
        """
        statement = (
            select(Conversation)
            .options(
                selectinload(
                    Conversation.assignments
                ).joinedload(
                    ConversationAssignment.assignee
                ),
                selectinload(
                    Conversation.assignments
                ).joinedload(
                    ConversationAssignment.assigner
                ),
                selectinload(
                    Conversation.messages
                ).selectinload(
                    Message.attachments
                ),
                selectinload(
                    Conversation.notes
                ).joinedload(
                    ConversationNote.author
                ),
                selectinload(
                    Conversation.sla_history
                ),
                joinedload(
                    Conversation.category
                ),
            )
            .where(
                Conversation.id == conversation_id
            )
        )

        return self.db.scalar(statement)

    def get_by_provider_id(
        self,
        provider: str,
        provider_conversation_id: str,
    ) -> Conversation | None:
        statement = (
            select(Conversation)
            .where(
                Conversation.provider == provider
            )
            .where(
                Conversation.provider_conversation_id
                == provider_conversation_id
            )
        )

        return self.db.scalar(statement)

    def add(
        self,
        conversation: Conversation,
    ) -> Conversation:
        self.db.add(conversation)
        return conversation

    def upsert_by_provider_id(
        self,
        provider: str,
        provider_conversation_id: str,
        values: dict,
    ) -> tuple[Conversation, bool]:
        conversation = self.get_by_provider_id(
            provider,
            provider_conversation_id,
        )

        created = conversation is None

        if created:
            creation_values = {
                'category_manually_selected': False,
                **values,
            }

            # provider is supplied explicitly to the model constructor below.
            # Remove any duplicate provider key from imported values.
            creation_values.pop('provider', None)

            conversation = Conversation(
                provider=provider,
                provider_conversation_id=provider_conversation_id,
                **creation_values,
            )

            self.db.add(conversation)

        else:
            for key, value in values.items():
                # Provider identity is immutable for an existing conversation.
                if key != 'provider':
                    setattr(
                        conversation,
                        key,
                        value,
                    )

        return conversation, created

    def _filtered_statement(
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
        conversation_ids: list[UUID] | None = None,
    ):
        """Build the reusable base conversation query."""
        statement = select(Conversation)

        if conversation_ids is not None:
            statement = statement.where(
                Conversation.id.in_(conversation_ids)
            )

        if search:
            normalized_search = (
                f'%{search.strip()}%'
            )

            message_match = exists(
                select(Message.id)
                .where(
                    Message.conversation_id
                    == Conversation.id
                )
                .where(
                    Message.body.ilike(
                        normalized_search
                    )
                )
            )

            note_match = exists(
                select(ConversationNote.id)
                .where(
                    ConversationNote.conversation_id
                    == Conversation.id
                )
                .where(
                    ConversationNote.deleted_at.is_(None)
                )
                .where(
                    ConversationNote.body.ilike(
                        normalized_search
                    )
                )
            )

            statement = statement.where(
                or_(
                    Conversation.subject.ilike(
                        normalized_search
                    ),
                    Conversation.buyer_identifier.ilike(
                        normalized_search
                    ),
                    Conversation.provider_conversation_id.ilike(
                        normalized_search
                    ),
                    Conversation.reference_id.ilike(
                        normalized_search
                    ),
                    message_match,
                    note_match,
                )
            )

        if status:
            statement = statement.where(
                Conversation.status == status
            )

        if provider:
            statement = statement.where(
                Conversation.provider == provider
            )

        if conversation_type:
            statement = statement.where(
                Conversation.provider_conversation_type
                == conversation_type
            )

        if provider_account_id:
            statement = statement.where(
                Conversation.provider_account_id
                == provider_account_id
            )

        if assigned_user_id:
            statement = statement.where(
                exists(
                    select(
                        ConversationAssignment.id
                    ).where(
                        and_(
                            ConversationAssignment.conversation_id
                            == Conversation.id,
                            ConversationAssignment.assigned_to
                            == assigned_user_id,
                            ConversationAssignment.unassigned_at.is_(
                                None
                            ),
                        )
                    )
                )
            )

        if category_id:
            statement = statement.where(
                Conversation.category_id
                == category_id
            )

        if date_from or date_to:
            # Date filtering must use actual message activity. Filtering only
            # conversation.created_at would incorrectly exclude old threads
            # that received a new buyer message during the requested period.
            message_in_period = select(
                Message.id
            ).where(
                Message.conversation_id
                == Conversation.id
            )

            if date_from:
                message_in_period = (
                    message_in_period.where(
                        Message.sent_at >= date_from
                    )
                )

            if date_to:
                message_in_period = (
                    message_in_period.where(
                        Message.sent_at < date_to
                    )
                )

            has_any_message = exists(
                select(Message.id).where(
                    Message.conversation_id
                    == Conversation.id
                )
            )

            # Newly imported conversations can temporarily exist before their
            # message rows are inserted. Only those message-less conversations
            # fall back to a conversation-level activity timestamp.
            conversation_activity_at = func.coalesce(
                Conversation.last_message_at,
                Conversation.external_created_at,
                Conversation.created_at,
            )

            conversation_in_period = ~has_any_message

            if date_from:
                conversation_in_period = and_(
                    conversation_in_period,
                    conversation_activity_at
                    >= date_from,
                )

            if date_to:
                conversation_in_period = and_(
                    conversation_in_period,
                    conversation_activity_at
                    < date_to,
                )

            statement = statement.where(
                or_(
                    exists(message_in_period),
                    conversation_in_period,
                )
            )

        return statement
