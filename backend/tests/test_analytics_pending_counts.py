from app.models.conversation import ConversationStatus
from app.services.analytics_service import AnalyticsService


def metric_value(metrics, label):
    return next(item['value'] for item in metrics if item['label'] == label)


def test_pending_conversations_count_uses_raw_conversation_status():
    service = AnalyticsService(db=None)
    rows = [
        {
            'status': ConversationStatus.PENDING.value,
            'is_replied': True,
            'is_overdue': False,
            'sla_compliant': None,
            'first_response_minutes': None,
            'reply_count': 1,
        },
        {
            'status': ConversationStatus.OPEN.value,
            'is_replied': False,
            'is_overdue': False,
            'sla_compliant': None,
            'first_response_minutes': None,
            'reply_count': 0,
        },
    ]

    pending = [row for row in rows if row['status'] == ConversationStatus.PENDING.value]

    assert len(pending) == 1


def test_status_distribution_uses_raw_status_not_calculated_status():
    service = AnalyticsService(db=None)
    rows = [
        {'status': ConversationStatus.PENDING.value, 'calculated_status': 'Replied'},
        {'status': ConversationStatus.OPEN.value, 'calculated_status': 'Not Read'},
    ]

    status_counts = service._count_by(rows, 'status', default='Unknown')

    assert metric_value(status_counts, ConversationStatus.PENDING.value) == 1
    assert metric_value(status_counts, ConversationStatus.OPEN.value) == 1
