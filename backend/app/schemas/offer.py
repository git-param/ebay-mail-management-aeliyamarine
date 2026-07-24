from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.offer import OfferDirection, OfferStatus


class OfferResponse(BaseModel):
    id: UUID
    account_id: UUID | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    provider_offer_id: str | None = None
    listing_id: str | None = None
    buyer_username: str | None = None
    offer_amount: Decimal | None = None
    currency: str | None = None
    status: str
    direction: str
    offer_type: str | None = None
    message: str | None = None
    raw_text: str | None = None
    expires_at: datetime | None = None
    created_at_provider: datetime | None = None
    created_at: datetime
    
    class Config:
        from_attributes = True
    
