from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Message


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[Message]:
        statement = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sent_at.asc())
        return list(self.db.scalars(statement))

    def get_by_provider_id(self, provider: str, provider_message_id: str) -> Message | None:
        statement = (
            select(Message)
            .where(Message.provider == provider)
            .where(Message.provider_message_id == provider_message_id)
        )
        return self.db.scalar(statement)

    def add(self, message: Message) -> Message:
        self.db.add(message)
        return message
