from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.sold_posting.models import SoldPostingStatus
from app.modules.sold_posting.service import SoldPostingService
from app.modules.sold_posting.status import normalize_sold_posting_status


def order(payment='PAID', fulfillment='NOT_STARTED', **extra):
    payload = {
        'orderId': 'ORDER-1',
        'orderPaymentStatus': payment,
        'orderFulfillmentStatus': fulfillment,
        'pricingSummary': {'total': {'value': '100.00', 'currency': 'USD'}},
        'paymentSummary': {'payments': [{'paymentStatus': 'PAID', 'paymentDate': '2026-07-27T10:00:00.000Z'}]},
        'lineItems': [{'lineItemId': 'LINE-1', 'legacyItemId': '123', 'title': 'Widget', 'quantity': 1, 'lineItemCost': {'value': '100.00', 'currency': 'USD'}}],
        'cancelStatus': {'cancelState': 'NONE'},
    }
    payload.update(extra)
    return payload


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        (order('NOT_PAID', 'NOT_STARTED'), SoldPostingStatus.AWAITING_PAYMENT),
        (order('PAID', 'NOT_STARTED'), SoldPostingStatus.AWAITING_SHIPMENT),
        (order('PAID', 'IN_PROGRESS'), SoldPostingStatus.PARTIALLY_SHIPPED),
        (order('PAID', 'FULFILLED'), SoldPostingStatus.SHIPPED),
        (order(cancelStatus={'cancelState': 'CANCELLED'}), SoldPostingStatus.CANCELLED),
        (order(cancelStatus={'cancelState': 'CANCEL_CLOSED'}), SoldPostingStatus.AWAITING_SHIPMENT),
        (order(paymentSummary={'payments': [], 'refunds': [{'amount': {'value': '100.00', 'currency': 'USD'}}]}), SoldPostingStatus.REFUNDED),
        (order(paymentSummary={'payments': [], 'refunds': [{'amount': {'value': '10.00', 'currency': 'USD'}}]}), SoldPostingStatus.PARTIALLY_REFUNDED),
        (order('SOME_FUTURE_STATUS', 'SOME_FUTURE_STATUS'), SoldPostingStatus.OTHER),
    ],
)
def test_normalized_status_mapping(payload, expected):
    assert normalize_sold_posting_status(payload) == expected


def test_map_order_handles_multiple_line_items_missing_sku_and_payment_date():
    service = SoldPostingService.__new__(SoldPostingService)
    service.repo = SimpleNamespace(resolve_image_url=lambda *args, **kwargs: None)
    account = SimpleNamespace(id=uuid4(), account_name='Store A', store_name=None, ebay_username='seller-a')
    payload = order(lineItems=[
        {'lineItemId': 'LINE-1', 'legacyItemId': '123', 'sku': '', 'title': 'First', 'quantity': 1, 'lineItemCost': {'value': '12.00', 'currency': 'USD'}},
        {'lineItemId': 'LINE-2', 'legacyItemId': '456', 'title': 'Second', 'quantity': 2, 'lineItemCost': {'value': '6.00', 'currency': 'USD'}},
    ])

    order_values, line_values = SoldPostingService._map_order(service, account, payload)

    assert order_values['order_id'] == 'ORDER-1'
    assert order_values['payment_date'] == datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
    assert order_values['normalized_status'] == SoldPostingStatus.AWAITING_SHIPMENT
    assert len(line_values) == 2
    assert line_values[0]['sku'] is None
    assert line_values[1]['sku'] is None


def test_filter_strategy_initial_and_incremental():
    service = SoldPostingService.__new__(SoldPostingService)
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    initial = SimpleNamespace(initial_sync_completed=False, last_successful_sync_at=None)
    incremental = SimpleNamespace(initial_sync_completed=True, last_successful_sync_at=datetime(2026, 7, 28, 11, 0, tzinfo=UTC))

    assert SoldPostingService._filter_for_state(service, initial, now).startswith('creationdate:[')
    assert 'lastmodifieddate:[2026-07-28T10:53:00.000Z..2026-07-28T12:00:00.000Z]' == SoldPostingService._filter_for_state(service, incremental, now)


def test_non_admin_forbidden_from_sync():
    service = SoldPostingService.__new__(SoldPostingService)
    user = SimpleNamespace(role=SimpleNamespace(name='AGENT'))
    with pytest.raises(HTTPException) as exc:
        SoldPostingService.assert_admin_can_sync(service, user)
    assert exc.value.status_code == 403
