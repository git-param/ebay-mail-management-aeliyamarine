from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator


class BestOfferConfigUpdate(BaseModel):
    enabled: StrictBool | None = None
    hours: StrictInt | None = Field(default=None, ge=0, le=168)
    minutes: StrictInt | None = Field(default=None, ge=0, le=59)
    account_ids: list[UUID] | None = None

    @model_validator(mode='after')
    def interval(self):
        if (self.hours is None) != (self.minutes is None):
            raise ValueError('Supply both hours and minutes')
        if self.hours is not None and not 2 <= self.hours * 60 + self.minutes <= 10080:
            raise ValueError('Interval must be between 2 minutes and 7 days')
        return self


class BestOfferSyncRequest(BaseModel):
    account_ids: list[UUID] | None = None


class BestOfferActionRequest(BaseModel):
    action: Literal['Accept', 'Decline', 'Counter']
    idempotency_key: UUID
    expected_version: StrictInt = Field(ge=1)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    quantity: StrictInt | None = Field(default=None, ge=1, le=100000)
    message: str | None = Field(default=None, max_length=250)

    @model_validator(mode='after')
    def counter(self):
        if self.action == 'Counter' and (self.amount is None or self.quantity is None):
            raise ValueError('Counter requires total amount and quantity')
        if self.action != 'Counter' and (self.amount is not None or self.quantity is not None):
            raise ValueError('Price and quantity are only valid for Counter')
        return self
