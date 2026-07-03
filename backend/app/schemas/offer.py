from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.offer import OfferDirection, OfferStatus


class OfferResponse(BaseModel):
    id: UUID
    provider_offer_id: str
    conversation_id: UUID
    listing_id: str
    buyer_username: str | None
    offer_amount: Decimal | None
    currency: str | None
    status: OfferStatus
    direction: OfferDirection
    offer_type: str | None
    quantity: int
    message: str | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {'from_attributes': True}
