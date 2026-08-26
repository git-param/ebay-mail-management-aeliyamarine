from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.conversation import Message, MessageSenderType
from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService


def test_is_inbound_message_prefers_buyer_sender():
    service = EbayMessageService.__new__(EbayMessageService)

    assert service._is_inbound_message(
        sender_normalized='n_ma067',
        recipient_normalized='aeliya110',
        seller_username='aeliya110',
        buyer_normalized='n_ma067',
    )


def test_is_inbound_message_uses_buyer_recipient_for_seller_message():
    service = EbayMessageService.__new__(EbayMessageService)

    assert not service._is_inbound_message(
        sender_normalized='aeliya110',
        recipient_normalized='n_ma067',
        seller_username='',
        buyer_normalized='n_ma067',
    )


def local_reply(*, provider_message_id: str, sent_at: datetime, body: str = 'Reply text') -> Message:
    return Message(
        provider='EBAY',
        provider_message_id=provider_message_id,
        sender_type=MessageSenderType.AGENT,
        sender_identifier='seller-name',
        recipient_identifier='buyer-name',
        body=body,
        read_status=True,
        is_inbound=False,
        sent_at=sent_at,
        raw_payload={'actor_id': 'agent-id'},
    )


def test_local_reply_match_selects_closest_unreconciled_reply():
    service = EbayMessageService.__new__(EbayMessageService)
    service.provider = 'EBAY'
    sent_at = datetime(2026, 8, 26, 4, 21, tzinfo=UTC)
    earlier = local_reply(
        provider_message_id='local-reply-earlier',
        sent_at=sent_at - timedelta(minutes=2),
    )
    closest = local_reply(
        provider_message_id='local-reply-closest',
        sent_at=sent_at - timedelta(seconds=3),
        body='Reply   text',
    )
    conversation = SimpleNamespace(messages=[earlier, closest])

    match = service._local_reply_match(
        conversation=conversation,
        body='Reply text',
        sent_at=sent_at,
        sender_username='SELLER-NAME',
        recipient_username='buyer-name',
    )

    assert match is closest


def test_local_reply_match_does_not_merge_unrelated_messages():
    service = EbayMessageService.__new__(EbayMessageService)
    service.provider = 'EBAY'
    sent_at = datetime(2026, 8, 26, 4, 21, tzinfo=UTC)
    candidates = [
        local_reply(provider_message_id='6411218285019', sent_at=sent_at),
        local_reply(provider_message_id='local-reply-wrong-body', sent_at=sent_at, body='Different reply'),
        local_reply(provider_message_id='local-reply-too-old', sent_at=sent_at - timedelta(minutes=6)),
        local_reply(provider_message_id='local-reply-wrong-recipient', sent_at=sent_at),
    ]
    candidates[-1].recipient_identifier = 'another-buyer'
    conversation = SimpleNamespace(messages=candidates)

    match = service._local_reply_match(
        conversation=conversation,
        body='Reply text',
        sent_at=sent_at,
        sender_username='seller-name',
        recipient_username='buyer-name',
    )

    assert match is None


def test_local_reply_matches_are_one_to_one_for_repeated_text():
    service = EbayMessageService.__new__(EbayMessageService)
    service.provider = 'EBAY'
    sent_at = datetime(2026, 8, 26, 4, 21, tzinfo=UTC)
    first = local_reply(provider_message_id='local-reply-first', sent_at=sent_at)
    second = local_reply(provider_message_id='local-reply-second', sent_at=sent_at + timedelta(seconds=20))
    conversation = SimpleNamespace(messages=[first, second])

    first_match = service._local_reply_match(
        conversation=conversation,
        body='Reply text',
        sent_at=sent_at,
        sender_username='seller-name',
        recipient_username='buyer-name',
    )
    first_match.provider_message_id = 'provider-first'
    second_match = service._local_reply_match(
        conversation=conversation,
        body='Reply text',
        sent_at=sent_at + timedelta(seconds=20),
        sender_username='seller-name',
        recipient_username='buyer-name',
    )

    assert first_match is first
    assert second_match is second


def test_sync_reconciles_local_reply_instead_of_creating_duplicate():
    sent_at = datetime(2026, 8, 26, 4, 21, tzinfo=UTC)
    reply = local_reply(
        provider_message_id='local-reply-existing',
        sent_at=sent_at - timedelta(seconds=2),
    )
    conversation = SimpleNamespace(
        id='conversation-id',
        provider_conversation_type='FROM_MEMBERS',
        buyer_identifier='buyer-name',
        messages=[reply],
    )

    class RepositoryDouble:
        def get_by_provider_id(self, provider, provider_message_id):
            return next(
                (
                    message
                    for message in conversation.messages
                    if message.provider == provider
                    and message.provider_message_id == provider_message_id
                ),
                None,
            )

        def upsert_by_provider_id(self, provider, provider_message_id, values):
            message = self.get_by_provider_id(provider, provider_message_id)
            assert message is reply
            for key, value in values.items():
                if key != 'provider':
                    setattr(message, key, value)
            return message, False

        def replace_attachments(self, message, attachments):
            assert message is reply
            assert attachments == []

    service = EbayMessageService.__new__(EbayMessageService)
    service.db = None
    service.provider = 'EBAY'
    service.message_repository = RepositoryDouble()
    account = SimpleNamespace(ebay_username='seller-name')
    detail = {
        'messages': [
            {
                'messageId': '6411218285019',
                'messageBody': 'Reply text',
                'senderUsername': 'seller-name',
                'recipientUsername': 'buyer-name',
                'readStatus': True,
                'createdDate': '2026-08-26T04:21:00Z',
            }
        ]
    }

    created_count, updated_count = service.upsert_messages(
        account=account,
        conversation=conversation,
        conversation_detail=detail,
    )

    assert created_count == 0
    assert updated_count == 1
    assert conversation.messages == [reply]
    assert reply.provider_message_id == '6411218285019'
    assert reply.raw_payload['actor_id'] == 'agent-id'
    assert reply.raw_payload['messageId'] == '6411218285019'
