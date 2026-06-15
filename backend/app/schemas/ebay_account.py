from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.ebay_account import EbayConnectionStatus, EbayEnvironment


class EbayAccountCreateRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=255)
    ebay_username: str = Field(min_length=1, max_length=255)
    environment: EbayEnvironment
    notes: str | None = None


class EbayAccountUpdateRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=255)
    ebay_username: str = Field(min_length=1, max_length=255)
    environment: EbayEnvironment
    notes: str | None = None


class EbayAccountResponse(BaseModel):
    id: UUID
    account_name: str
    ebay_username: str
    environment: EbayEnvironment
    connection_status: EbayConnectionStatus
    is_active: bool
    oauth_state: str | None
    token_expires_at: datetime | None
    ebay_user_id: str | None
    last_sync_at: datetime | None
    sync_status: str | None
    notes: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
