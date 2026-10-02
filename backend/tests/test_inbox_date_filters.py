from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine

import app.db.base  # Register relationships used by the conversation model.
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.utils.inbox_dates import InboxDate, inbox_date_bounds


def test_query_parsing_preserves_dates_and_exclusive_midnight_timestamps():
    adapter = TypeAdapter(InboxDate | None)
    date_only = adapter.validate_python('2026-01-02')
    midnight = adapter.validate_python('2026-01-03T00:00:00Z')
    assert type(date_only) is date
    assert type(midnight) is datetime
    assert inbox_date_bounds(date_only, midnight) == (
        datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC),
    )


def test_local_timestamp_bounds_are_not_extended_again():
    start, end = inbox_date_bounds(
        datetime.fromisoformat('2026-01-02T00:00:00+05:30'),
        datetime.fromisoformat('2026-02-03T00:00:00+05:30'),
    )
    assert start == datetime(2026, 1, 1, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 2, 2, 18, 30, tzinfo=UTC)


def test_date_only_api_clients_keep_inclusive_to_date():
    assert inbox_date_bounds(date(2026, 1, 2), date(2026, 1, 2)) == (
        datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert inbox_date_bounds(None, None) == (None, None)
    assert inbox_date_bounds(date(2026, 1, 2), None)[1] is None
    assert inbox_date_bounds(None, date(2026, 1, 2))[0] is None
    with pytest.raises(HTTPException) as error:
        inbox_date_bounds(date(2026, 2, 2), date(2026, 1, 2))
    assert error.value.status_code == 422


def test_range_matches_last_update_and_excludes_final_midnight():
    metadata = MetaData()
    conversations = Table('conversations', metadata,
        Column('id', String, primary_key=True),
        Column('last_message_at', DateTime), Column('updated_at', DateTime),
    )
    messages = Table('messages', metadata,
        Column('id', String, primary_key=True), Column('conversation_id', String), Column('sent_at', DateTime),
    )
    engine = create_engine('sqlite://')
    metadata.create_all(engine)
    ids = [uuid4() for _ in range(5)]
    start, end = inbox_date_bounds(date(2026, 1, 2), date(2026, 2, 2))
    with engine.begin() as connection:
        connection.execute(conversations.insert(), [
            {'id': ids[0].hex, 'last_message_at': datetime(2026, 1, 2), 'updated_at': datetime(2026, 9, 1)},
            {'id': ids[1].hex, 'last_message_at': datetime(2026, 2, 2, 23, 59, 59, 999999), 'updated_at': datetime(2026, 9, 1)},
            {'id': ids[2].hex, 'last_message_at': datetime(2026, 2, 3), 'updated_at': datetime(2026, 1, 2)},
            {'id': ids[3].hex, 'last_message_at': datetime(2026, 9, 1), 'updated_at': datetime(2026, 1, 2)},
            {'id': ids[4].hex, 'last_message_at': None, 'updated_at': datetime(2026, 1, 15)},
        ])
        # A January message in a thread last updated in September must not match.
        connection.execute(messages.insert(), {'id': uuid4().hex, 'conversation_id': ids[3].hex, 'sent_at': datetime(2026, 1, 15)})
        query = ConversationRepository(None)._filtered_statement(date_from=start, date_to=end).with_only_columns(Conversation.id)
        assert set(connection.scalars(query)) == {ids[0], ids[1], ids[4]}
