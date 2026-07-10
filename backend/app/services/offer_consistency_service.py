from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.offer import Offer


class OfferConsistencyService:
    """Keep Conversation.has_offers aligned with persisted offer rows."""

    def __init__(self, db: Session):
        self.db = db

    def sync_conversation(self, conversation_id: UUID | None) -> bool:
        if not conversation_id:
            return False

        has_offers = bool(
            self.db.scalar(
                select(func.count(Offer.id) > 0).where(Offer.conversation_id == conversation_id)
            )
        )
        conversation = self.db.get(Conversation, conversation_id)
        if conversation and conversation.has_offers != has_offers:
            conversation.has_offers = has_offers
            self.db.flush()
        return has_offers

    def sync_conversations(self, conversation_ids) -> None:
        for conversation_id in {value for value in conversation_ids if value}:
            self.sync_conversation(conversation_id)
