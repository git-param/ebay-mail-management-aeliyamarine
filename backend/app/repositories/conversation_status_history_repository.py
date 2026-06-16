from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationStatusHistory


class ConversationStatusHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[ConversationStatusHistory]:
        statement = (
            select(ConversationStatusHistory)
            .where(ConversationStatusHistory.conversation_id == conversation_id)
            .order_by(ConversationStatusHistory.changed_at.desc())
        )
        return list(self.db.scalars(statement))

    def add(self, status_history: ConversationStatusHistory) -> ConversationStatusHistory:
        self.db.add(status_history)
        return status_history
