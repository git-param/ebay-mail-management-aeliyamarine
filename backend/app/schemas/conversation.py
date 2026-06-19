from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.conversation import ConversationStatus, MessageSenderType, SyncLogStatus


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
    response_due_at: datetime | None = None
    status: ConversationStatus
    category_id: UUID | None
    category: CategoryBriefResponse | None = None
    last_message_at: datetime | None
    external_created_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_assignment: 'ConversationAssignmentResponse | None' = None
    seller_account: EbayAccountBriefResponse | None = None


class MessageResponse(BaseModel):
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


class ConversationDetailResponse(ConversationSummaryResponse):
    current_assignee_id: UUID | None = None
    messages: list[MessageResponse] = Field(default_factory=list)
    assignments: list['ConversationAssignmentResponse'] = Field(default_factory=list)
    notes: list['ConversationNoteResponse'] = Field(default_factory=list)


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
