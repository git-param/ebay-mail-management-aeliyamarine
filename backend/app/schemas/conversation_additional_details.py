from pydantic import BaseModel, Field


class AdditionalDetailRow(BaseModel):
    label: str
    value: str


class AdditionalDetailSection(BaseModel):
    title: str
    rows: list[AdditionalDetailRow] = Field(default_factory=list)


class AdditionalOrderDetails(BaseModel):
    order_id: str
    sections: list[AdditionalDetailSection] = Field(default_factory=list)


class ConversationAdditionalDetailsResponse(BaseModel):
    orders: list[AdditionalOrderDetails] = Field(default_factory=list)
