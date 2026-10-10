import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.order_buyer_conversation_service import OrderBuyerConversationService
from app.services import new_buyer_conversation_service as new_buyers
from app.services import order_buyer_conversation_service as order_buyers
from app.services.order_context_service import OrderContextService
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

    service = OrderBuyerConversationService(db)
    service.attach_order = Mock()
    result = service.resolve(order.order_id, account_id)
    if existing:
        service.attach_order.assert_called_once_with(thread, order)
        db.commit.assert_called_once()
    else:
        service.attach_order.assert_not_called()

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
    resolver.attach_order.assert_called_once_with(thread, order)
    reply_service.send_reply.assert_awaited_once()


def test_existing_thread_first_send_also_attaches_exact_order(monkeypatch):
    existing = SimpleNamespace(id=uuid4())
    service, db, account, reply_service, payload = new_buyer_fixture(monkeypatch, existing=existing)
    order = SimpleNamespace(order_id='order-123', buyer_username='actual-buyer')
    resolver = Mock(get_order=Mock(return_value=order))
    monkeypatch.setattr(new_buyers, 'OrderBuyerConversationService', Mock(return_value=resolver))
    payload['order_id'] = order.order_id
    asyncio.run(service.send_first_message(**payload))
    resolver.attach_order.assert_called_once_with(existing, order)
    db.add.assert_not_called()


def test_attaches_exact_order_and_preserves_full_payload(monkeypatch):
    account_id = uuid4()
    conversation = SimpleNamespace(id=uuid4(), provider_account_id=account_id, buyer_identifier='buyer')
    sold = SimpleNamespace(
        order_id='order-123', ebay_account_id=account_id, buyer_username='buyer',
        raw_payload_json={'buyer': {'username': 'buyer', 'buyerRegistrationAddress': {'fullName': 'Name'}},
                          'orderPaymentStatus': 'PAID'},
        order_payment_status='PAID', order_fulfillment_status='FULFILLED',
        line_items=[SimpleNamespace(
            line_item_id='line-1', legacy_item_id='123', sku='sku', title='Product', quantity=1,
            image_url='image', raw_payload_json={}, line_item_cost=10, currency='USD',
        )],
    )
    context = Mock()
    context.repository.get_by_order_id.return_value = None
    monkeypatch.setattr(order_buyers, 'OrderContextService', Mock(return_value=context))
    db = Mock()
    OrderBuyerConversationService(db).attach_order(conversation, sold)
    payload = context.upsert_order_payload.call_args.kwargs['payload']
    assert payload['orderId'] == sold.order_id
    assert payload['buyer']['buyerRegistrationAddress']['fullName'] == 'Name'
    assert payload['lineItems'][0]['legacyItemId'] == '123'
    assert conversation.reference_id == '123'
    assert context.link_conversation_context.call_args.kwargs['conversation_detail']['orderId'] == sold.order_id
    assert context.link_conversation_context.return_value.match_strategy == 'SOLD_POSTING'
    assert 'orderId' not in sold.raw_payload_json


def test_order_attachment_rejects_different_buyer_or_account():
    account_id = uuid4()
    thread = SimpleNamespace(provider_account_id=account_id, buyer_identifier='buyer')
    for order_account, order_buyer in [(uuid4(), 'buyer'), (account_id, 'other-buyer')]:
        sold = SimpleNamespace(ebay_account_id=order_account, buyer_username=order_buyer)
        with pytest.raises(HTTPException) as exc:
            OrderBuyerConversationService(Mock()).attach_order(thread, sold)
        assert exc.value.status_code == 400


def test_sync_keeps_explicit_sold_posting_order_mapping():
    service = OrderContextService(Mock())
    mapping = SimpleNamespace(match_strategy='SOLD_POSTING', order_record_id=uuid4())
    service.repository = Mock()
    service.repository.get_mapping.return_value = mapping
    assert service.link_conversation_context(conversation=SimpleNamespace(id=uuid4())) is mapping
    service.repository.upsert_mapping.assert_not_called()
