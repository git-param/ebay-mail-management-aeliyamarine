from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.conversation import ConversationStatus, MessageSenderType, SyncLogStatus


class ConversationSummaryResponse(BaseModel):
    id: UUID
    provider: str
    provider_conversation_id: str
    provider_account_id: UUID | None
    subject: str | None
    buyer_identifier: str | None
    status: ConversationStatus
    category_id: UUID | None
    last_message_at: datetime | None
    external_created_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationSummaryResponse):
    current_assignee_id: UUID | None = None


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    provider: str
    provider_message_id: str
    sender_type: MessageSenderType
    sender_identifier: str | None
    body: str
    is_inbound: bool
    sent_at: datetime
    created_at: datetime


class ConversationAssignmentResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    assigned_to: UUID
    assigned_by: UUID
    assigned_at: datetime
    unassigned_at: datetime | None


class AssignConversationRequest(BaseModel):
    assigned_to: UUID


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
