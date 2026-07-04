from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.offer import OfferDirection, OfferStatus


class OfferResponse(BaseModel):
    id: UUID
    provider_offer_id: str | None
    listing_id: str | None = None  
    buyer_username: str | None
    offer_amount: Decimal | None
    currency: str | None
    status: str
    direction: str
    offer_type: str | None
    message: str | None
    expires_at: datetime | None
    created_at: datetime
    
    class Config:
        from_attributes = True
    
