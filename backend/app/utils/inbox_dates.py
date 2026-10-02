"""Normalize inbox date filters without expanding timestamp upper bounds."""
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import HTTPException
from pydantic import BeforeValidator


def parse_inbox_date(value):
    if isinstance(value, str):
        return date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value)
    return value


InboxDate = Annotated[datetime | date, BeforeValidator(parse_inbox_date)]


def inbox_date_bounds(date_from: datetime | date | None, date_to: datetime | date | None):
    def bound(value, *, end=False):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        # Date-only clients retain inclusive UTC calendar-day semantics.
        return datetime.combine(value + timedelta(days=1) if end else value, time.min, tzinfo=UTC)

    start, end = bound(date_from), bound(date_to, end=True)
    if start is not None and end is not None and start >= end:
        raise HTTPException(422, 'From date must be on or before To date')
    return start, end
