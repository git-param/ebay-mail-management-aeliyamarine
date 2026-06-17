from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.conversation import Conversation, ConversationAssignment, ConversationNote, ConversationStatus, Message


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
        provider_account_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        category_id: UUID | None = None,
    ) -> list[Conversation]:
        statement = self._filtered_statement(
            search=search,
            status=status,
            provider=provider,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
        ).options(
            selectinload(Conversation.assignments).joinedload(ConversationAssignment.assignee),
            selectinload(Conversation.assignments).joinedload(ConversationAssignment.assigner),
            selectinload(Conversation.messages),
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
        provider_account_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        category_id: UUID | None = None,
    ) -> int:
        statement = self._filtered_statement(
            search=search,
            status=status,
            provider=provider,
            provider_account_id=provider_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
        )
        return int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)

    def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        statement = (
            select(Conversation)
            .options(
                selectinload(Conversation.assignments).joinedload(ConversationAssignment.assignee),
                selectinload(Conversation.assignments).joinedload(ConversationAssignment.assigner),
                selectinload(Conversation.messages),
                selectinload(Conversation.notes).joinedload(ConversationNote.author),
                joinedload(Conversation.category),
            )
            .where(Conversation.id == conversation_id)
        )
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
            conversation = Conversation(
                provider=provider,
                provider_conversation_id=provider_conversation_id,
                **values,
            )
            self.db.add(conversation)
        else:
            for key, value in values.items():
                setattr(conversation, key, value)
        return conversation, created

    def _filtered_statement(
        self,
        *,
        search: str | None = None,
        status: ConversationStatus | None = None,
        provider: str | None = None,
        provider_account_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        category_id: UUID | None = None,
    ):
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
        return statement
