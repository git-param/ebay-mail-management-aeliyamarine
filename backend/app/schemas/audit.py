from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditUserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: str


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    user: AuditUserResponse | None = None
    action: str
    entity_type: str | None
    entity_id: UUID | None
    category: str | None
    status: str | None
    metadata: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogPageResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
