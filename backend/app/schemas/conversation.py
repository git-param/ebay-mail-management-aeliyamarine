from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.conversation import ConversationStatus, MessageSenderType, SyncLogStatus
from app.schemas.offer import OfferResponse


class UserBriefResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    role: str


class CategoryBriefResponse(BaseModel):
    id: UUID
    name: str
    color: str


class EbayAccountBriefResponse(BaseModel):
    id: UUID
    account_name: str
    ebay_username: str
    store_name: str | None = None


class ConversationSummaryResponse(BaseModel):
    """Conversation row returned by inbox list and detail endpoints."""

    id: UUID
    provider: str
    provider_conversation_id: str
    provider_account_id: UUID | None
    subject: str | None
    buyer_identifier: str | None
    provider_conversation_status: str | None = None
    provider_conversation_type: str | None = None
    reference_id: str | None = None
    reference_type: str | None = None
    unread_count: int = 0
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_direction: str | None = None
    calculated_status: str | None = None
    is_not_read: bool = False
    is_replied: bool = False
    response_due_at: datetime | None = None
    status: ConversationStatus
    category_id: UUID | None
    category_manually_selected: bool = False
    category: CategoryBriefResponse | None = None
    last_message_at: datetime | None
    external_created_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_assignment: 'ConversationAssignmentResponse | None' = None
    seller_account: EbayAccountBriefResponse | None = None


class MessageResponse(BaseModel):
    """API representation of a conversation message."""

    id: UUID
    conversation_id: UUID
    provider: str
    provider_message_id: str
    sender_type: MessageSenderType
    sender_identifier: str | None
    recipient_identifier: str | None = None
    body: str
    read_status: bool | None = None
    is_inbound: bool
    sent_at: datetime
    created_at: datetime
    attachments: list['MessageAttachmentResponse'] = Field(default_factory=list)
    attachment_delivery_warning: str | None = None


class MessageAttachmentResponse(BaseModel):
    """API representation of a message attachment."""

    id: UUID
    message_id: UUID
    account_id: UUID | None = None
    provider: str
    provider_attachment_id: str | None = None
    file_name: str
    media_name: str | None = None
    media_url: str | None = None
    media_type: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    download_url: str | None = None
    created_at: datetime


class ReplyValidationResponse(BaseModel):
    valid: bool
    violations: list[str] = Field(default_factory=list)


class ReplyConversationRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ConversationDetailResponse(ConversationSummaryResponse):
    suggested_message_type_id: UUID | None = None
    current_assignee_id: UUID | None = None
    messages: list[MessageResponse] = Field(default_factory=list)
    offers: list[OfferResponse] = Field(default_factory=list)
    assignments: list['ConversationAssignmentResponse'] = Field(default_factory=list)
    notes: list['ConversationNoteResponse'] = Field(default_factory=list)
    product_context: 'ConversationProductContextResponse | None' = None
    order_context: 'OrderContextResponse | None' = None


class ConversationProductContextResponse(BaseModel):
    reference_id: str = ''
    title: str = ''
    image_url: str = ''
    seller_username: str = ''
    item_url: str = ''
    sku: str | None = None
    order_id: str | None = None
    price: float | None = None
    currency: str = ''
    offer_available: bool = False
    buy_now_available: bool = False
    cta_type: str = ''
    enrichment_status: str = ''


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    target_language: str = Field(default='en', min_length=2, max_length=10)


class TranslationResponse(BaseModel):
    translated_text: str
    detected_language: str | None = None


class OrderLineItemResponse(BaseModel):
    id: UUID
    item_id: str | None = None
    listing_id: str | None = None
    sku: str | None = None
    title: str | None = None
    image_url: str | None = None
    quantity: int | None = None
    price_value: float | None = None
    price_currency: str | None = None


class ReturnContextResponse(BaseModel):
    id: UUID
    return_id: str
    return_status: str | None = None
    return_reason: str | None = None
    return_state: str | None = None
    created_date: datetime | None = None
    ebay_url: str


class CancellationContextResponse(BaseModel):
    id: UUID
    cancel_id: str
    cancel_state: str | None = None
    cancel_reason: str | None = None
    requester: str | None = None
    created_date: datetime | None = None
    ebay_url: str


class OrderContextOrderResponse(BaseModel):
    id: UUID
    order_id: str
    buyer_username: str | None = None
    payment_status: str | None = None
    fulfillment_status: str | None = None
    cancel_status: str | None = None
    refund_status: str | None = None
    pricing_summary: dict | None = None
    refunds: list | None = None
    line_items: list[OrderLineItemResponse] = Field(default_factory=list)
    returns: list[ReturnContextResponse] = Field(default_factory=list)
    cancellations: list[CancellationContextResponse] = Field(default_factory=list)
    ebay_url: str


class OrderLinkingResponse(BaseModel):
    strategy: str
    requires_manual_selection: bool = False


class OrderContextResponse(BaseModel):
    selected_order: OrderContextOrderResponse | None = None
    candidate_orders: list[OrderContextOrderResponse] = Field(default_factory=list)
    linking: OrderLinkingResponse
    deep_links: dict[str, str] = Field(default_factory=dict)


class ConversationOrderContextCardResponse(BaseModel):
    order_id: str = ''
    sku: str = ''
    title: str = ''
    image_url: str = ''
    buyer: str = ''
    inventory_id: str = ''


class SelectConversationOrderRequest(BaseModel):
    order_record_id: UUID | None = None


class ConversationPageResponse(BaseModel):
    items: list[ConversationSummaryResponse]
    total: int
    limit: int
    offset: int


class ConversationAssignmentResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    assigned_to: UUID
    assigned_by: UUID
    assigned_at: datetime
    unassigned_at: datetime | None
    assignee: UserBriefResponse | None = None
    assigner: UserBriefResponse | None = None


class AssignConversationRequest(BaseModel):
    assigned_to: UUID


class BulkConversationUpdateRequest(BaseModel):
    conversation_ids: list[UUID] = Field(min_length=1, max_length=500)
    assigned_to: UUID | None = None
    category_id: UUID | None = None
    assign_to_category_owners: bool = False
    status: ConversationStatus | None = None


class BulkConversationUpdateResponse(BaseModel):
    updated_count: int
    assignment_count: int = 0
    skipped_count: int = 0
    message: str


class ConversationNoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class ConversationNoteResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    author_id: UUID
    body: str
    created_at: datetime
    updated_at: datetime
    author: UserBriefResponse | None = None


class UpdateConversationStatusRequest(BaseModel):
    status: ConversationStatus
    note: str | None = Field(default=None, max_length=1000)


class UpdateConversationCategoryRequest(BaseModel):
    category_id: UUID | None
    note: str | None = Field(default=None, max_length=1000)


class SyncLogResponse(BaseModel):
    id: UUID
    provider: str
    provider_account_id: UUID | None
    sync_type: str
    status: SyncLogStatus
    started_at: datetime
    completed_at: datetime | None
    records_processed: int
    error_message: str | None
