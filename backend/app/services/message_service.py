from uuid import UUID

from sqlalchemy.orm import Session

from app.models.conversation import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.conversation_service import ConversationService


class MessageService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = MessageRepository(db)
        self.conversation_repository = ConversationRepository(db)

    def list_messages(self, conversation_id: UUID) -> list[Message]:
        ConversationService(self.db).get_conversation(conversation_id)
        return self.repository.list_by_conversation(conversation_id)

    def add_message(self, message: Message) -> Message:
        self.repository.add(message)
        conversation = self.conversation_repository.get_by_id(message.conversation_id)
        if conversation and (not conversation.last_message_at or message.sent_at > conversation.last_message_at):
            conversation.last_message_at = message.sent_at
        self.db.commit()
        self.db.refresh(message)
        return message
