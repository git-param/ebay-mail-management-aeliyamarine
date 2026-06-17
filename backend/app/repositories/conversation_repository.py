from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[Conversation]:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.assignments))
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        )
        if offset:
            statement = statement.offset(offset)
        if limit:
            statement = statement.limit(limit)
        return list(self.db.scalars(statement))

    def count(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Conversation)) or 0)

    def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.assignments), selectinload(Conversation.messages))
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
