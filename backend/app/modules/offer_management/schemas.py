from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.offer_management.models import OfferManagementOutcome, OfferManagementStatus
from app.modules.offer_management.utils import extract_listing_id


class OfferEntryBase(BaseModel):
    offer_date: date
    ebay_account_id: UUID
    ebay_account_name: str | None = None
    listing_id: str
    listing_url: str | None = None
    sku: str | None = None
    product_title: str | None = None
    condition: str | None = None
    listing_quantity: int | None = None
    offer_quantity: int | None = None
    currency: str = 'USD'
    listed_price: Decimal | None = None
    revised_price: Decimal | None = None
    automated_offer_price: Decimal | None = None
    buyer_offer_price: Decimal | None = None
    counteroffer_price: Decimal | None = None
    final_price: Decimal | None = None
    buyer_id: str | None = None
    status: OfferManagementStatus = OfferManagementStatus.OPEN
    outcome: OfferManagementOutcome = OfferManagementOutcome.PENDING
    is_vip_lead: bool = False
    next_offer_followup: date | None = None
    follow_up_1_notes: str | None = None
    follow_up_2_notes: str | None = None
    remarks: str | None = None
    related_conversation_id: UUID | None = None
    related_offer_id: UUID | None = None

    @field_validator('listing_id')
    @classmethod
    def validate_listing_id(cls, value):
        return extract_listing_id(value)

    @field_validator('currency')
    @classmethod
    def validate_currency(cls, value):
        code = str(value or '').strip().upper()
        if not (3 <= len(code) <= 10):
            raise ValueError('Currency must be an ISO-style code.')
        return code

    @field_validator('listed_price', 'revised_price', 'automated_offer_price', 'buyer_offer_price', 'counteroffer_price', 'final_price')
    @classmethod
    def validate_money(cls, value):
        if value is not None and value < 0:
            raise ValueError('Money values cannot be negative.')
        return value

    @field_validator('listing_quantity', 'offer_quantity')
    @classmethod
    def validate_quantity(cls, value):
        if value is not None and value <= 0:
            raise ValueError('Quantity must be greater than zero.')
        return value


class OfferEntryCreate(OfferEntryBase):
    pass


class OfferEntryUpdate(BaseModel):
    offer_date: date | None = None
    ebay_account_id: UUID | None = None
    ebay_account_name: str | None = None
    listing_id: str | None = None
    listing_url: str | None = None
    sku: str | None = None
    product_title: str | None = None
    condition: str | None = None
    listing_quantity: int | None = None
    offer_quantity: int | None = None
    currency: str | None = None
    listed_price: Decimal | None = Field(default=None)
    revised_price: Decimal | None = Field(default=None)
    automated_offer_price: Decimal | None = Field(default=None)
    buyer_offer_price: Decimal | None = Field(default=None)
    counteroffer_price: Decimal | None = Field(default=None)
    final_price: Decimal | None = Field(default=None)
    buyer_id: str | None = None
    status: OfferManagementStatus | None = None
    outcome: OfferManagementOutcome | None = None
    is_vip_lead: bool | None = None
    next_offer_followup: date | None = None
    follow_up_1_notes: str | None = None
    follow_up_2_notes: str | None = None
    remarks: str | None = None
    related_conversation_id: UUID | None = None
    related_offer_id: UUID | None = None


class OfferEntryResponse(OfferEntryBase):
    id: UUID
    entry_number: int
    created_by_user_id: UUID
    updated_by_user_id: UUID | None = None
    is_high_value: bool
    created_at: datetime
    updated_at: datetime
    agent_name: str | None = None
    related_conversation_ref: str | None = None

    class Config:
        from_attributes = True


class OfferEntryListResponse(BaseModel):
    items: list[OfferEntryResponse]
    total: int
    page: int
    page_size: int


class OfferEntryHistoryResponse(BaseModel):
    id: UUID
    offer_entry_id: UUID
    changed_by_user_id: UUID | None = None
    action: str
    previous_values: dict | None = None
    new_values: dict | None = None
    changed_at: datetime
    changed_by_name: str | None = None

    class Config:
        from_attributes = True


class OfferLookupRequest(BaseModel):
    listing: str


class OfferLookupMatch(BaseModel):
    offer_id: UUID
    buyer_id: str | None = None
    offer_type: str | None = None
    offer_amount: Decimal | None = None
    currency: str | None = None
    offer_date: datetime | None = None
    offer_status: str | None = None
    seller_account: str | None = None
    seller_account_id: UUID | None = None
    related_conversation_id: UUID | None = None
    related_conversation: str | None = None


class OfferLookupResponse(BaseModel):
    listing_id: str
    listing_url: str
    details: dict
    matches: list[OfferLookupMatch] = []
    selected: dict | None = None
    message: str


class OfferSummaryResponse(BaseModel):
    total_entries: int
    open_offers: int
    follow_ups_due: int
    awaiting_payment: int
    sold: int
    high_value_offers: int


class OfferBulkDeleteRequest(BaseModel):
    entry_ids: list[UUID]


class OfferBulkDeleteResponse(BaseModel):
    deleted_count: int
