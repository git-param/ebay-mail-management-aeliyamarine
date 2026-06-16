from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[Conversation]:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.assignments))
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        )
        return list(self.db.scalars(statement))

    def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.assignments))
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
