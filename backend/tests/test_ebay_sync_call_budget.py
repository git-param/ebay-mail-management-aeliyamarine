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


def test_incremental_sync_includes_boundary_activity_in_overlap_window():
    service = EbaySyncService.__new__(EbaySyncService)
    checkpoint = datetime(2026, 9, 28, 12, tzinfo=UTC)
    service._get_conversations_with_retry = Mock(side_effect=[
        SimpleNamespace(
            ok=True,
            payload={
                'total': 1,
                'conversations': [{
                    'conversationId': 'boundary',
                    'latestMessage': {'createdDate': checkpoint.isoformat()},
                }],
            },
        ),
        SimpleNamespace(ok=True, payload={'total': 0, 'conversations': []}),
    ])

    summaries = list(service._iter_conversation_summaries(
        SimpleNamespace(id='account'),
        updated_since=checkpoint - timedelta(minutes=5),
    ))

    assert [summary['conversationId'] for summary, _ in summaries] == ['boundary']


def test_conversation_detail_pagination_is_merged_for_reconciliation():
    service = EbaySyncService.__new__(EbaySyncService)
    service._get_conversation_detail_with_retry = Mock(side_effect=[
        SimpleNamespace(
            status_code=200,
            ok=True,
            payload={'total': 2, 'messages': [{'messageId': 'first'}]},
            request_url='first',
            request_headers={},
            response_headers={},
        ),
        SimpleNamespace(
            status_code=200,
            ok=True,
            payload={'total': 2, 'messages': [{'messageId': 'second'}]},
            request_url='second',
            request_headers={},
            response_headers={},
        ),
    ])

    response = service._get_full_conversation_detail(
        SimpleNamespace(access_token='token'),
        conversation_id='conversation',
        conversation_type='FROM_MEMBERS',
    )

    assert [message['messageId'] for message in response.payload['messages']] == ['first', 'second']
    assert [call.kwargs['offset'] for call in service._get_conversation_detail_with_retry.call_args_list] == [0, 50]
