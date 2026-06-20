from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Message, MessageAttachment


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

    def replace_attachments(self, message: Message, attachments: list[MessageAttachment]) -> None:
        message.attachments.clear()
        for attachment in attachments:
            message.attachments.append(attachment)

    def upsert_by_provider_id(self, provider: str, provider_message_id: str, values: dict) -> tuple[Message, bool]:
        message = self.get_by_provider_id(provider, provider_message_id)
        created = message is None
        if created:
            message = Message(
                provider=provider,
                provider_message_id=provider_message_id,
                **values,
            )
            self.db.add(message)
        else:
            for key, value in values.items():
                setattr(message, key, value)
        return message, created
