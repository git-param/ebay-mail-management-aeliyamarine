from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.category import Category
from app.models.conversation import Conversation, ConversationAssignment, ConversationNote, ConversationStatus, Message, MessageAttachment


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
        visible_category_ids: set[UUID] | None = None,
        visibility_user_id: UUID | None = None,
    ) -> list[Conversation]:
        """List conversations filtered by search criteria and optional agent visibility."""
        statement = self._filtered_statement(
            search=search,
            status=status,
            provider=provider,
            conversation_type=conversation_type,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
            visible_category_ids=visible_category_ids,
            visibility_user_id=visibility_user_id,
        ).options(
            selectinload(Conversation.assignments).joinedload(ConversationAssignment.assignee),
            selectinload(Conversation.assignments).joinedload(ConversationAssignment.assigner),
            selectinload(Conversation.messages).selectinload(Message.attachments),
            selectinload(Conversation.offers),
            joinedload(Conversation.category),
        ).order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
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
        visible_category_ids: set[UUID] | None = None,
        visibility_user_id: UUID | None = None,
    ) -> int:
        """Count conversations with the same filters used by the list endpoint."""
        statement = self._filtered_statement(
            search=search,
            status=status,
            provider=provider,
            conversation_type=conversation_type,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
            visible_category_ids=visible_category_ids,
            visibility_user_id=visibility_user_id,
        )
        return int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)

    def get_by_id(
        self,
        conversation_id: UUID,
        visible_category_ids: set[UUID] | None = None,
        visibility_user_id: UUID | None = None,
    ) -> Conversation | None:
        """Fetch a conversation only when it matches the optional visibility scope."""
        statement = (
            select(Conversation)
            .options(
                selectinload(Conversation.assignments).joinedload(ConversationAssignment.assignee),
                selectinload(Conversation.assignments).joinedload(ConversationAssignment.assigner),
                selectinload(Conversation.messages).selectinload(Message.attachments),
                selectinload(Conversation.offers),
                selectinload(Conversation.notes).joinedload(ConversationNote.author),
                joinedload(Conversation.category),
            )
            .where(Conversation.id == conversation_id)
        )
        if visible_category_ids is not None and visibility_user_id is not None:
            statement = statement.where(self._agent_visibility_filter(visible_category_ids, visibility_user_id))
        elif visible_category_ids is not None:
            statement = statement.where(Conversation.category_id.in_(visible_category_ids))
        return self.db.scalar(statement)

    def get_by_provider_id(self, provider: str, provider_conversation_id: str) -> Conversation | None:
        statement = (
            select(Conversation)
            .where(Conversation.provider == provider)
            .where(Conversation.provider_conversation_id == provider_conversation_id)
        )
        return self.db.scalar(statement)

    def add(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        return conversation

    def upsert_by_provider_id(self, provider: str, provider_conversation_id: str, values: dict) -> tuple[Conversation, bool]:
        conversation = self.get_by_provider_id(provider, provider_conversation_id)
        created = conversation is None
        if created:
            # Remove provider from values to avoid duplicate keyword argument
            creation_values = {'category_manually_selected': False, **values}
            creation_values.pop('provider', None)  # <-- add this line
            conversation = Conversation(
                provider=provider,
                provider_conversation_id=provider_conversation_id,
                **creation_values,
            )
            self.db.add(conversation)
        else:
            for key, value in values.items():
                if key != 'provider':  # skip provider to be safe
                    setattr(conversation, key, value)
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
        visible_category_ids: set[UUID] | None = None,
        visibility_user_id: UUID | None = None,
    ):
        """Build the base conversation query with optional agent visibility filtering."""
        statement = select(Conversation)
        if search:
            normalized_search = f'%{search.strip()}%'
            message_match = exists(
                select(Message.id)
                .where(Message.conversation_id == Conversation.id)
                .where(Message.body.ilike(normalized_search))
            )
            statement = statement.where(
                or_(
                    Conversation.subject.ilike(normalized_search),
                    Conversation.buyer_identifier.ilike(normalized_search),
                    Conversation.provider_conversation_id.ilike(normalized_search),
                    Conversation.reference_id.ilike(normalized_search),
                    message_match,
                )
            )
        if status:
            statement = statement.where(Conversation.status == status)
        if provider:
            statement = statement.where(Conversation.provider == provider)
        if conversation_type:
            statement = statement.where(Conversation.provider_conversation_type == conversation_type)
        if provider_account_id:
            statement = statement.where(Conversation.provider_account_id == provider_account_id)
        if assigned_user_id:
            statement = statement.where(
                exists(
                    select(ConversationAssignment.id).where(
                        and_(
                            ConversationAssignment.conversation_id == Conversation.id,
                            ConversationAssignment.assigned_to == assigned_user_id,
                            ConversationAssignment.unassigned_at.is_(None),
                        )
                    )
                )
            )
        if category_id:
            statement = statement.where(Conversation.category_id == category_id)
        if visible_category_ids is not None and visibility_user_id is not None:
            statement = statement.where(self._agent_visibility_filter(visible_category_ids, visibility_user_id))
        elif visible_category_ids is not None:
            statement = statement.where(Conversation.category_id.in_(visible_category_ids))
        return statement

    def _agent_visibility_filter(self, visible_category_ids: set[UUID], user_id: UUID):
        """Allow category-scoped inbox visibility plus explicit assignments."""
        assigned_to_user = exists(
            select(ConversationAssignment.id).where(
                and_(
                    ConversationAssignment.conversation_id == Conversation.id,
                    ConversationAssignment.assigned_to == user_id,
                    ConversationAssignment.unassigned_at.is_(None),
                )
            )
        )
        # A direct assignment remains visible even when its category is outside
        # the agent's normal queue; explicit ownership takes precedence.
        return or_(Conversation.category_id.in_(visible_category_ids), assigned_to_user)
