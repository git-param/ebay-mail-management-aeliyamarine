from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.conversation_additional_details import AdditionalDetailSection


class LiveReturnDetails(BaseModel):
    return_id: str
    order_id: str
    sections: list[AdditionalDetailSection] = Field(default_factory=list)
    warning: str | None = None


class ConversationLiveReturnsResponse(BaseModel):
    order_id: str
    returns: list[LiveReturnDetails] = Field(default_factory=list)
    fetched_at: datetime
    next_offset: int | None = None
