from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationCategoryHistory


class ConversationCategoryHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[ConversationCategoryHistory]:
        statement = (
            select(ConversationCategoryHistory)
            .where(ConversationCategoryHistory.conversation_id == conversation_id)
            .order_by(ConversationCategoryHistory.changed_at.desc())
        )
        return list(self.db.scalars(statement))

    def add(self, category_history: ConversationCategoryHistory) -> ConversationCategoryHistory:
        self.db.add(category_history)
        return category_history
