from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

class EbayConnectRequest(BaseModel):
    account_id: UUID


class EbayManualCallbackRequest(BaseModel):
    state: str = Field(min_length=1)
    code: str = Field(min_length=1)


class EbayConnectResponse(BaseModel):
    authorization_url: str
    state: str


class EbayOAuthCallbackResponse(BaseModel):
    account_id: UUID
    connection_status: str
    ebay_username: str
    ebay_user_id: str | None = None
    seller_account_id: str | None = None
    store_name: str | None = None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
    message: str


class EbayRefreshTokenResponse(BaseModel):
    account_id: UUID
    connection_status: str
    access_token_expires_at: datetime | None
    message: str


class EbayTestConnectionResponse(BaseModel):
    connected: bool
    account_status: str
    account_id: UUID
    access_token_expires_at: datetime | None


class EbayApiUsageResponse(BaseModel):
    usage_date: str
    api_name: str
    call_count: int
    daily_limit: int
    remaining: int


class EbayApiUsageListResponse(BaseModel):
    items: list[EbayApiUsageResponse]


class EbayAutoSyncStatusResponse(BaseModel):
    enabled: bool
    interval_hours: int
    latest_sync_at: datetime | None = None
    next_run_at: datetime | None = None


class EbayAutoSyncToggleRequest(BaseModel):
    enabled: bool


class EbaySyncResultResponse(BaseModel):
    account_id: UUID
    ebay_username: str
    sync_log_id: UUID
    status: str
    conversations_processed: int
    conversations_failed: int
    failed_conversation_ids: list[str]
    conversations_created: int
    conversations_updated: int
    messages_created: int
    messages_updated: int
    total_conversations_available: int | None = None
    elapsed_seconds: float | None = None
    average_detail_seconds: float | None = None
    error_message: str | None = None
    api_usage: EbayApiUsageResponse | None = None


class EbaySyncAllResponse(BaseModel):
    results: list[EbaySyncResultResponse]
    api_usage: EbayApiUsageListResponse
