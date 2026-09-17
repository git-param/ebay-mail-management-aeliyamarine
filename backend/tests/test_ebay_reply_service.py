from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.conversation import MessageSenderType
from app.services.ebay_reply_service import EbayReplyService


def conversation(**overrides):
    values = {
        'buyer_identifier': 'buyer-name',
        'provider_conversation_id': 'conversation-123',
        'provider_conversation_type': 'FROM_MEMBERS',
        'reference_id': 'listing-123',
        'reference_type': 'LISTING',
        'subject': 'Existing eBay thread',
        'order_mapping': SimpleNamespace(
            ebay_item_id='order-item-123',
            listing_id='listing-123',
        ),
        'linked_order': None,
        'messages': [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_send_context_prefers_existing_conversation_id_over_trading_context():
    service = EbayReplyService.__new__(EbayReplyService)

    context = service._send_context(conversation())

    assert context == {
        'transport': 'conversation',
        'call_name': 'send_conversation_message',
        'conversation_id': 'conversation-123',
        'conversation_type': 'FROM_MEMBERS',
    }


def test_send_context_falls_back_to_trading_when_conversation_id_is_missing():
    service = EbayReplyService.__new__(EbayReplyService)

    context = service._send_context(
        conversation(provider_conversation_id='')
    )

    assert context['transport'] == 'trading'
    assert context['call_name'] == 'AddMemberMessageAAQToPartner'
    assert context['item_id'] == 'order-item-123'
    assert context['recipient_id'] == 'buyer-name'


def test_send_context_uses_rtq_parent_message_only_without_conversation_id():
    service = EbayReplyService.__new__(EbayReplyService)
    inbound_message = SimpleNamespace(
        is_inbound=True,
        provider_message_id='parent-message-123',
        sent_at=datetime(2026, 9, 17, 8, 0, tzinfo=UTC),
        sender_type=MessageSenderType.CUSTOMER,
    )

    context = service._send_context(
        conversation(
            provider_conversation_id='',
            order_mapping=None,
            linked_order=None,
            messages=[inbound_message],
        )
    )

    assert context == {
        'transport': 'trading',
        'call_name': 'AddMemberMessageRTQ',
        'item_id': 'listing-123',
        'recipient_id': 'buyer-name',
        'parent_message_id': 'parent-message-123',
    }


def test_send_context_requires_buyer_identifier():
    service = EbayReplyService.__new__(EbayReplyService)

    with pytest.raises(HTTPException) as exc:
        service._send_context(conversation(buyer_identifier=''))

    assert exc.value.status_code == 400
