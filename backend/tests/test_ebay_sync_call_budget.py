from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.integrations.ebay.services.ebay_sync_service import EbaySyncService


def test_incremental_sync_stops_after_old_summary_page():
    service = EbaySyncService.__new__(EbaySyncService)
    cutoff = datetime(2026, 9, 28, 12, tzinfo=UTC)
    old_timestamp = (cutoff - timedelta(days=1)).isoformat()
    service._get_conversations_with_retry = Mock(return_value=SimpleNamespace(
        ok=True,
        payload={
            'total': 500,
            'conversations': [{'conversationId': 'old', 'createdDate': old_timestamp}],
        },
    ))

    summaries = list(service._iter_conversation_summaries(
        SimpleNamespace(id='account'), updated_since=cutoff,
    ))

    assert summaries == []
    assert service._get_conversations_with_retry.call_count == 2
    assert [call.kwargs['conversation_type'] for call in service._get_conversations_with_retry.call_args_list] == [
        'FROM_MEMBERS', 'FROM_EBAY',
    ]
    assert all(call.kwargs['offset'] == 0 for call in service._get_conversations_with_retry.call_args_list)
