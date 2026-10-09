import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.order_buyer_conversation_service import OrderBuyerConversationService
from app.services import new_buyer_conversation_service as new_buyers
from test_new_buyer_conversations import new_buyer_fixture


@pytest.mark.parametrize('existing', [True, False])
def test_order_conversation_resolves_the_buyer_within_the_owning_account(existing):
    account_id = uuid4()
    order = SimpleNamespace(
        order_id='order-123', ebay_account_id=account_id,
        ebay_account_name='Main', buyer_username=' buyer-from-order ',
    )
    thread = SimpleNamespace(id=uuid4()) if existing else None
    db = Mock()
    db.scalar.side_effect = [order, thread]

    result = OrderBuyerConversationService(db).resolve(order.order_id, account_id)

    assert result['buyer_username'] == 'buyer-from-order'
    assert result['account_id'] == account_id
    assert result['conversation_id'] == (thread.id if thread else None)
    order_query, conversation_query = [call.args[0] for call in db.scalar.call_args_list]
    assert account_id in order_query.compile().params.values()
    assert account_id in conversation_query.compile().params.values()
    assert 'buyer-from-order' in conversation_query.compile().params.values()


@pytest.mark.parametrize('order, status', [
    (None, 404),
    (SimpleNamespace(buyer_username=None), 422),
])
def test_missing_order_or_buyer_does_not_launch_a_message(order, status):
    db = Mock()
    db.scalar.return_value = order
    with pytest.raises(HTTPException) as exc:
        OrderBuyerConversationService(db).resolve('missing-order', uuid4())
    assert exc.value.status_code == status
    assert db.scalar.call_count == 1


def test_order_first_message_uses_authoritative_buyer_and_listing(monkeypatch):
    service, db, account, reply_service, payload = new_buyer_fixture(monkeypatch)
    order = SimpleNamespace(
        order_id='order-123', buyer_username='actual-order-buyer',
        line_items=[SimpleNamespace(legacy_item_id='listing-123')],
    )
    resolver = Mock(get_order=Mock(return_value=order))
    monkeypatch.setattr(new_buyers, 'OrderBuyerConversationService', Mock(return_value=resolver))
    payload['order_id'] = order.order_id
    payload['buyer_username'] = 'tampered-url-buyer'

    asyncio.run(service.send_first_message(**payload))

    resolver.get_order.assert_called_once_with(order.order_id, account.id)
    thread = db.add.call_args.args[0]
    assert thread.buyer_identifier == 'actual-order-buyer'
    assert thread.provider_account_id == account.id
    assert thread.subject == 'Order order-123'
    assert thread.reference_id == 'listing-123'
    assert thread.reference_type == 'LISTING'
    reply_service.send_reply.assert_awaited_once()
