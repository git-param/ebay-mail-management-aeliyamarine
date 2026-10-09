from uuid import UUID

from sqlalchemy.orm import Session

from app.services.audit_service import AuditService
from app.services.conversation_service import ConversationService
from app.utils.conversation_read_state import apply_read_state


class ConversationReadStateService:
    def __init__(self, db: Session):
        self.db = db

    def update(self, conversation_ids: list[UUID], *, is_read: bool, actor_id: UUID) -> int:
        service = ConversationService(self.db)
        # Resolve every ID first, so a missing conversation cannot cause a partial update.
        conversations = [service.get_conversation(value) for value in dict.fromkeys(conversation_ids)]
        try:
            for conversation in conversations:
                apply_read_state(conversation, is_read)
                AuditService(self.db).log(
                    action='CONVERSATION_MARKED_READ' if is_read else 'CONVERSATION_MARKED_UNREAD',
                    user_id=actor_id,
                    entity_type='CONVERSATION',
                    entity_id=conversation.id,
                    category='MESSAGE_MANAGEMENT',
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return len(conversations)
