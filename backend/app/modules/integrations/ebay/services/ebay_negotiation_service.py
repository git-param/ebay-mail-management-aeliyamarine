from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.offer import Offer, OfferStatus
from app.services.offer_consistency_service import OfferConsistencyService


class EbayNegotiationService:
    """Read locally persisted buyer offers and historical seller offers."""

    def __init__(self, db: Session):
        self.db = db

    def conversation_offers(self, conversation_id: UUID) -> list[Offer]:
        conversation = self.db.get(Conversation, conversation_id)
        if conversation and not conversation.has_offers:
            return []

        offers = list(self.db.scalars(
            select(Offer).where(Offer.conversation_id == conversation_id).order_by(Offer.created_at.desc())
        ))
        if not offers:
            OfferConsistencyService(self.db).sync_conversation(conversation_id)
            self.db.flush()
            return []

        now = datetime.now(UTC)
        changed = False
        for offer in offers:
            if offer.status == OfferStatus.PENDING and offer.expires_at and offer.expires_at <= now:
                offer.status = OfferStatus.EXPIRED
                changed = True
        if changed:
            self.db.commit()
        return offers
