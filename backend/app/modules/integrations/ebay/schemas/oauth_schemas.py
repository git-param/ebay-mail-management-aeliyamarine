from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EbayConnectRequest(BaseModel):
    account_id: UUID


class EbayConnectResponse(BaseModel):
    authorization_url: str
    state: str


class EbayOAuthCallbackResponse(BaseModel):
    account_id: UUID
    connection_status: str
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
