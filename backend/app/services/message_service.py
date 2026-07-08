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
        conversation = ConversationService(self.db).get_conversation(conversation_id)
        messages = self.repository.list_by_conversation(conversation_id)

        # Safety: never expose offer cards for FROM_EBAY conversations.
        if (conversation.provider_conversation_type or '').upper() == 'FROM_EBAY':
            changed = False
            for message in messages:
                if getattr(message, 'offer_data', None) is not None:
                    message.offer_data = None
                    changed = True

            if changed:
                self.db.commit()

        return messages

    def add_message(self, message: Message) -> Message:
        self.repository.add(message)
        conversation = self.conversation_repository.get_by_id(message.conversation_id)
        if conversation and (not conversation.last_message_at or message.sent_at > conversation.last_message_at):
            conversation.last_message_at = message.sent_at
        self.db.commit()
        self.db.refresh(message)
        return message