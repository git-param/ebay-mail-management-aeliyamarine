from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
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
        offers = list(self.db.scalars(
            select(Offer)
            .where(Offer.conversation_id == conversation_id)
            .order_by(func.coalesce(Offer.created_at_provider, Offer.created_at).asc(), Offer.created_at.asc())
        ))
        if not offers and conversation:
            offers = self._link_unattached_offers(conversation)
        if not offers:
            OfferConsistencyService(self.db).sync_conversation(conversation_id)
            self.db.flush()
            return []
        if conversation and not conversation.has_offers:
            conversation.has_offers = True
            self.db.flush()

        now = datetime.now(UTC)
        changed = False
        for offer in offers:
            if offer.status == OfferStatus.PENDING and offer.expires_at and offer.expires_at <= now:
                offer.status = OfferStatus.EXPIRED
                changed = True
        if changed:
            self.db.commit()
        return offers

    def _link_unattached_offers(self, conversation: Conversation) -> list[Offer]:
        account_id = conversation.provider_account_id
        listing_id = str(conversation.reference_id or "").strip()
        buyer = str(conversation.buyer_identifier or "").strip().lower()
        if not account_id or not listing_id or not buyer:
            return []

        offers = list(
            self.db.scalars(
                select(Offer)
                .where(
                    Offer.provider == "EBAY",
                    Offer.account_id == account_id,
                    Offer.conversation_id.is_(None),
                    Offer.listing_id == listing_id,
                    func.lower(func.coalesce(Offer.buyer_username, "")) == buyer,
                )
                .order_by(func.coalesce(Offer.created_at_provider, Offer.created_at).asc(), Offer.created_at.asc())
            )
        )
        for offer in offers:
            offer.conversation_id = conversation.id
        if offers:
            self.db.flush()
        return offers
